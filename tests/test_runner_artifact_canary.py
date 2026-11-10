import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "runner-artifact-canary.yml"

REQUIRED_INPUTS = (
    "roll_id",
    "candidate",
    "canary_label",
    "templates_sha",
    "expected_runner_prefix",
    "expected_engine",
    "ssh_user",
)

# Byte-for-byte the formats gate-hub generates: canary_window.py:60-67
# (canary-<12hex>-<node>-ci) and slot naming gatehub-<candidate12>-slot-<n>.
INPUT_VALIDATION_PATTERNS = {
    "roll_id": r"\[\[ \"\$ROLL_ID\" =~ \^\[A-Za-z0-9\]\[A-Za-z0-9._-\]\{0,63\}\$ ",
    "candidate": r"\[\[ \"\$CANDIDATE\" =~ \^\[0-9a-f\]\{40\}\$ ",
    "canary_label": r"\[\[ \"\$CANARY_LABEL\" =~ \^canary-\[0-9a-f\]\{12\}-\[a-z0-9\]\[a-z0-9-\]\*-ci\$ ",
    "templates_sha": r"\[\[ \"\$TEMPLATES_SHA\" =~ \^\[0-9a-f\]\{40\}\$ ",
    "expected_runner_prefix": r"\[\[ \"\$EXPECTED_RUNNER_PREFIX\" =~ \^gatehub-\[0-9a-f\]\{12\}-slot-\$ ",
    "expected_engine": r"\[\[ \"\$EXPECTED_ENGINE\" =~ \^\[0-9\]\+\\\.\[0-9\]\+\\\.\[0-9\]\+\$ ",
    # Same shape guard as ci-templates build-deploy.yml's ssh_user.
    "ssh_user": r"\[\[ \"\$SSH_USER\" =~ \^\[a-z_\]\[a-z0-9_-\]\{0,31\}\$ ",
}

# Card C (gate-hub release pipeline) consumes this receipt; the field set is
# the serialization contract and must not silently shrink.
RECEIPT_FIELDS = (
    "schema",
    "roll_id",
    "candidate",
    "canary_label",
    "runner_name",
    "job_id",
    "job_labels",
    "templates_sha",
    "docker_server_version",
    "acr_ref",
    "acr_digest",
    "deploy_host",
    "deploy_image_id",
    "deploy_repo_digests",
    "local_ref",
    "local_tag",
    "local_digest",
    "local_pull",
    "cleanup",
    "verdict",
    "failure_reason",
)

CANARY_RUNS_ON = (
    'runs-on: [self-hosted, linux, "${{ needs.validate-inputs.outputs.canary_label }}"]'
)


def step_block(text, step_name):
    """Raw YAML text of the named step, up to the next step boundary."""
    start = text.index(f"      - name: {step_name}")
    next_boundary = text.find("\n      - name: ", start + 1)
    return text[start:next_boundary if next_boundary != -1 else len(text)]


def job_block(text, job_key):
    """Raw YAML text of one top-level job, up to the next 2-space-indented job key."""
    start = text.index(f"  {job_key}:\n")
    rest = text[start + len(f"  {job_key}:\n"):]
    boundary = re.search(r"\n  [a-z]", rest)
    return text[start:start + len(f"  {job_key}:\n") + boundary.start()] if boundary else text[start:]


class RunnerArtifactCanaryWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text()

    def test_dispatch_inputs_all_required(self):
        on_block = self.text[self.text.index("  workflow_dispatch:"):self.text.index("permissions:")]
        for name in REQUIRED_INPUTS:
            self.assertIn(f"      {name}:", on_block, name)
        self.assertEqual(on_block.count("        required: true"), len(REQUIRED_INPUTS))
        self.assertNotIn("required: false", on_block)

    def test_hosted_job_validates_every_input_format(self):
        validate = step_block(self.text, "Validate dispatch inputs")
        for name, pattern in INPUT_VALIDATION_PATTERNS.items():
            self.assertRegex(validate, pattern, name)
        # Invalid input must emit the failure marker and fail the job.
        self.assertIn("RUNNER-ARTIFACT-CANARY-FAIL reason=invalid-input-$1", validate)
        self.assertIn("exit 1", validate)
        self.assertIn('echo "canary_label=$CANARY_LABEL" >> "$GITHUB_OUTPUT"', validate)

    def test_canary_job_routes_exactly_through_canary_label(self):
        self.assertIn(CANARY_RUNS_ON, self.text)
        # Canary slots drop the ordinary lane label `ci`; no runs-on in this
        # workflow may reintroduce it.
        for match in re.finditer(r"^    runs-on: (.+)$", self.text, re.MULTILINE):
            self.assertNotIn(" ci", match.group(1), match.group(0))
        # The actual job labels are re-checked against the GitHub jobs API
        # inside the identity step, not just trusted from runs-on.
        identity = step_block(self.text, "Record runner identity and enforce engine contract")
        self.assertIn('os.environ["EXPECTED_CANARY_LABEL"] not in job["labels"]', identity)
        self.assertIn("job-label-missing-canary-label", identity)

    def test_ci_templates_checked_out_at_pinned_templates_sha(self):
        checkout = step_block(self.text, "Checkout ci-templates at pinned SHA")
        self.assertIn("repository: zlxlabs/ci-templates", checkout)
        self.assertIn("ref: ${{ inputs.templates_sha }}", checkout)
        self.assertIn("persist-credentials: false", checkout)
        self.assertNotIn("ref: main", checkout)
        self.assertNotIn("ref: v1", checkout)

    def test_push_calls_real_script_with_unique_tag_and_single_attempt(self):
        push = step_block(self.text, "Build and push probe image to ACR")
        self.assertIn("scripts/push_to_acr.sh", push)
        self.assertIn(
            'printf \'%s\' "${ROLL_ID}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}" '
            "| tr -c 'A-Za-z0-9._-' '-'",
            push,
        )
        self.assertIn("PUSH_MAX_ATTEMPTS=1", push)
        # The local-registry leg (gate-hub#2246) must go through the script's
        # own opt-in dual-push path; the job env supplies LOCAL_REGISTRY.
        self.assertNotIn("LOCAL_REGISTRY=''", push)
        self.assertIn("FROM scratch", push)
        self.assertIn("password-stdin", push)

    def test_local_registry_job_env_constant_and_inherited_by_push_script(self):
        env_block = job_block(self.text, "canary")
        env_block = env_block[:env_block.index("    steps:")]
        # Job-level constant, same level as ACR_REGISTRY; non-empty and the
        # exact MagicDNS name (the registry cert covers only this name).
        self.assertIn("LOCAL_REGISTRY: zlx-vm-work-i7-ci-runner.taile9071.ts.net:5001", env_block)
        # push_to_acr.sh reads LOCAL_REGISTRY from its environment; the push
        # step must not shadow the job env with an override.
        push = step_block(self.text, "Build and push probe image to ACR")
        self.assertNotIn("LOCAL_REGISTRY=", push)

    def test_local_digest_readback_uses_registry_side_query(self):
        readback = step_block(self.text, "Read back local registry digest")
        # Registry-side query only — docker image inspect would read the local
        # daemon cache and prove nothing about the push landing.
        self.assertIn("docker buildx imagetools inspect \"$ref\" --format '{{json .Manifest}}'", readback)
        self.assertNotIn("docker image inspect", readback)
        # Well-formed sha256 manifest digest, stored for the receipt and
        # exported as a step output for the n305 local-pull leg.
        self.assertIn("grep -qE '^sha256:[0-9a-f]{64}$'", readback)
        self.assertIn('printf \'%s\' "$digest" > "$RUNNER_TEMP/canary-local-digest"', readback)
        self.assertIn('echo "local_digest=$digest" >> "$GITHUB_OUTPUT"', readback)

    def test_local_pull_step_is_advisory_only(self):
        local_pull = step_block(self.text, "Pull probe image from local registry on deploy host")
        # rc must be captured with an explicit if so the receipt can record
        # the outcome; continue-on-error would hide the status from it.
        self.assertNotIn("continue-on-error", local_pull)
        # Plain if/else capture (no `!`): with `if ! cmd`, $? inside the else
        # branch would be the negated status, not the ssh rc.
        self.assertIn("if remote_out=", local_pull)
        self.assertNotIn("if ! remote_out=", local_pull)
        self.assertIn("rc=$?", local_pull)
        # The step never fails the job: no failure marker, no exit 1, and an
        # unconditional exit 0 at the end.
        self.assertNotIn("RUNNER-ARTIFACT-CANARY-FAIL", local_pull)
        self.assertNotIn("exit 1", local_pull)
        self.assertTrue(local_pull.rstrip().endswith("exit 0"))
        # Same ssh credentials and known_hosts wiring as the ACR deploy leg.
        self.assertIn('ssh -i "$HOME/.ssh/id_deploy"', local_pull)
        # pass requires RepoDigests to carry exactly <local_ref>@<local_digest>.
        self.assertIn('grep -qF "\\"$local_ref@$LOCAL_DIGEST\\""', local_pull)
        # Receipt files for all three statuses.
        self.assertIn("canary-local-pull-status", local_pull)
        self.assertIn("canary-local-pull-digests", local_pull)
        # local_pull must not feed the verdict (see the receipt verdict line).
        receipt = step_block(self.text, "Write receipt")
        self.assertNotIn("local_pull_ok", receipt.split("verdict =")[1].splitlines()[0])

    def test_deploy_host_runs_only_pull_inspect_rmi_over_ssh(self):
        deploy = step_block(self.text, "Pull, inspect and remove probe image on deploy host")
        self.assertIn("docker pull '$ref'", deploy)
        self.assertIn("docker image inspect --format '{{.Id}}' '$ref'", deploy)
        self.assertIn("docker image inspect --format '{{json .RepoDigests}}' '$ref'", deploy)
        self.assertIn("docker rmi '$ref'", deploy)
        self.assertIn('grep -q "\\"$acr_image@sha256:"', deploy)
        self.assertIn("DEPLOY_HOST: 100.68.21.80", self.text)
        # The deploy SSH user comes from the dispatch input, never a hardcoded
        # value in this public workflow file.
        self.assertIn("DEPLOY_SSH_USER: ${{ inputs.ssh_user }}", self.text)
        for forbidden in ("docker compose", "docker-compose", "docker run", "docker start",
                          "docker restart", "systemctl"):
            self.assertNotIn(forbidden, deploy)

    def test_cleanup_step_always_runs_and_verifies_absence(self):
        cleanup = step_block(self.text, "Delete ACR tag and verify removal")
        self.assertIn("if: always()", cleanup)
        # ACR personal: registry v2 delete only accepts a digest (tag DELETE
        # returns 400 DIGEST_INVALID — verified against the live registry).
        self.assertIn("-X DELETE -H \"Authorization: Bearer $token\"", cleanup)
        self.assertIn('"https://$ACR_REGISTRY/v2/$repo/manifests/$digest")', cleanup)
        # Read-back proof: the tag must be gone, verbatim "no such manifest".
        self.assertIn('grep -q \'no such manifest\'', cleanup)
        self.assertIn("fail cleanup-verify-tag-still-exists", cleanup)
        self.assertIn("fail cleanup-verify-inconclusive", cleanup)
        self.assertIn('echo "::error::RUNNER-ARTIFACT-CANARY-FAIL reason=$1"', cleanup)

    def test_upload_artifact_step_always_runs(self):
        upload = step_block(self.text, "Upload receipt artifact")
        self.assertIn("if: always()", upload)
        self.assertIn("runner-artifact-canary-receipt.v1.json", upload)
        self.assertIn("if-no-files-found: error", upload)

    def test_receipt_contains_full_contract_field_set(self):
        receipt = step_block(self.text, "Write receipt")
        self.assertIn('"runner-artifact-canary-receipt.v1"', receipt)
        for field in RECEIPT_FIELDS:
            self.assertIn(f'"{field}"', receipt, field)
        self.assertIn(
            'verdict = "pass" if (identity_ok and push_ok and deploy_ok and cleanup_ok and local_ok) else "fail"',
            receipt,
        )
        # Local push/read-back failure is a hard gate with its own reason;
        # the receipt re-validates the digest shape itself.
        self.assertIn('failure_reason = "local-push-failed" if not local_ok else "unknown-step-failure"', receipt)
        self.assertIn('re.fullmatch(r"sha256:[0-9a-f]{64}", local_digest)', receipt)
        # Contract object: status + repo_digests, digest null when invalid.
        self.assertIn('"local_digest": local_digest if local_ok else None', receipt)
        self.assertIn('"status": local_pull_status', receipt)
        self.assertIn('"repo_digests": json.loads(read_file("canary-local-pull-digests") or "[]")', receipt)

    def test_failure_marker_is_emitted_and_job_fails(self):
        for step_name in ("Record runner identity and enforce engine contract",
                          "Build and push probe image to ACR",
                          "Read back local registry digest",
                          "Pull, inspect and remove probe image on deploy host",
                          "Delete ACR tag and verify removal"):
            block = step_block(self.text, step_name)
            self.assertIn("RUNNER-ARTIFACT-CANARY-FAIL reason=", block, step_name)
            self.assertIn("exit 1", block, step_name)

    def test_timeouts_keep_workflow_within_fifteen_minutes(self):
        self.assertIn("timeout-minutes: 2", job_block(self.text, "validate-inputs"))
        self.assertIn("timeout-minutes: 12", job_block(self.text, "canary"))

    def test_all_actions_pinned_to_full_commit_sha(self):
        uses = re.findall(r"^\s+uses: (\S+)", self.text, re.MULTILINE)
        self.assertGreaterEqual(len(uses), 2)
        for use in uses:
            self.assertRegex(use, r"^[^@]+@[0-9a-f]{40}$", use)

    def test_no_tailscale_step_or_ts_authkey(self):
        # The canary job only runs on self-hosted canary slots (hosts already in
        # the tailnet, build-deploy.yml self-mode wiring); a tailscale step
        # would dangle an extra ephemeral node per run and cannot succeed in the
        # DinD slot shape. Its absence and the secret non-dependency are locked.
        self.assertNotIn("tailscale/github-action", self.text)
        self.assertNotIn("TS_AUTHKEY", self.text)

    def test_only_shared_secrets_are_used(self):
        used = sorted(set(re.findall(r"secrets\.([A-Z_]+)", self.text)))
        self.assertEqual(used, ["ACR_PASSWORD", "ACR_USERNAME", "KNOWN_HOSTS",
                                "SSH_DEPLOY_KEY"])


if __name__ == "__main__":
    unittest.main()
