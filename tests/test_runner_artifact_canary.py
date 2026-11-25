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

    def test_push_script_failure_records_acr_push_failed(self):
        push = step_block(self.text, "Build and push probe image to ACR")
        # Capture push_to_acr.sh rc with plain if/else so set -e cannot
        # exit before the fail helper writes canary-failure-reason.
        # `if ! cmd` would make $? inside else the negated status (always 0).
        self.assertIn("if PUSH_MAX_ATTEMPTS=1", push)
        self.assertIn("push_rc=$?", push)
        self.assertNotIn("if ! PUSH_MAX_ATTEMPTS", push)
        self.assertIn('[ "$push_rc" -ne 0 ]', push)
        self.assertIn("fail acr-push-failed", push)
        self.assertIn(
            'printf \'%s\' "$1" > "$RUNNER_TEMP/canary-failure-reason"',
            push,
        )
        self.assertIn("exit 1", push)

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

    def test_local_pull_step_is_hard_gate_for_verdict(self):
        local_pull = step_block(self.text, "Pull probe image from local registry on deploy host")
        # gate-hub#2459: the local pull decides the verdict. rc must still be
        # captured with an explicit plain if/else (no `!` so $? inside else is
        # the real ssh rc) so every outcome lands in the receipt status file.
        self.assertNotIn("continue-on-error", local_pull)
        self.assertIn("if remote_out=", local_pull)
        self.assertNotIn("if ! remote_out=", local_pull)
        self.assertIn("rc=$?", local_pull)
        self.assertIn("canary-local-pull-status", local_pull)
        self.assertIn("canary-local-pull-digests", local_pull)
        # pass requires RepoDigests to carry exactly <local_ref>@<local_digest>.
        self.assertIn('grep -qF "\\"$local_ref@$LOCAL_DIGEST\\""', local_pull)
        # Failure is hard: reason recorded, error marker emitted via the fail
        # helper (same shape as the other hard-gate steps), step exits
        # non-zero so the job and the verdict fail.
        self.assertIn("fail local-pull-failed", local_pull)
        self.assertIn('echo "::error::RUNNER-ARTIFACT-CANARY-FAIL reason=$1"', local_pull)
        self.assertIn('printf \'%s\' "$1" > "$RUNNER_TEMP/canary-failure-reason"', local_pull)
        self.assertIn("exit 1", local_pull)
        # Missing prerequisites cannot invent a local-pull failure: status
        # skipped with exit 0 — the push/read-back leg already failed with its
        # own reason (masking it would corrupt the receipt's failure_reason).
        self.assertIn("printf 'skipped' > \"$status_file\"", local_pull)
        self.assertIn("::notice::local pull skipped", local_pull)
        self.assertNotIn("local-pull-failed", local_pull.split("::notice::")[0])
        # Same ssh credentials and known_hosts wiring as the ACR advisory leg.
        self.assertIn('ssh -i "$HOME/.ssh/id_deploy"', local_pull)
        # Success path ends the step cleanly; the receipt (if: always()) and
        # the artifact upload still run afterwards.
        self.assertTrue(local_pull.rstrip().endswith("exit 0"))
        # The receipt verdict formula must include local_pull_ok.
        receipt = step_block(self.text, "Write receipt")
        self.assertIn("local_pull_ok", receipt.split("verdict =")[1].splitlines()[0])

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
        # gate-hub#2459: the public-ACR pull leg is advisory — failures emit the
        # ACR-ADVISORY warning (via the advisory helper) and never fail the job
        # or write a failure reason; observed values still go to
        # deploy_image_id/deploy_repo_digests.
        self.assertIn("advisory deploy-host-pull-inspect-rmi-failed", deploy)
        self.assertIn('echo "::warning::RUNNER-ARTIFACT-CANARY-ACR-ADVISORY reason=$1"', deploy)
        self.assertNotIn("RUNNER-ARTIFACT-CANARY-FAIL", deploy)
        # The run body must not write the failure reason (the step-block text
        # extends into the next step's comment, which mentions the literal;
        # cut the body at the blank line before the next comment).
        run_body = deploy.split("run: |", 1)[1].split("\n\n      #", 1)[0]
        self.assertNotIn("canary-failure-reason", run_body)
        self.assertIn("exit 0", deploy)
        # No step-level exit 1: the only exit 1 inside this block is the remote
        # pull_ok guard inside the ssh payload (it turns a remote failure into
        # a non-zero ssh rc, which the advisory() branch converts to a warning).
        for line in deploy.splitlines():
            if "exit 1" in line:
                self.assertIn("pull_ok", line)

    def test_deploy_host_pull_retries_three_attempts_advisory_only(self):
        deploy = step_block(self.text, "Pull, inspect and remove probe image on deploy host")
        # Bounded pull retry: max 3 attempts, 20s/40s intervals, each failure
        # greppable on remote stderr. gate-hub#2459: the historical ACR-timeout
        # reason literal survives as the advisory reason vocabulary for
        # gate-hub's acr_advisory_status.
        self.assertEqual(deploy.count("docker pull '$ref'"), 1)
        self.assertIn("for attempt in 1 2 3; do", deploy)
        self.assertIn("CANARY-DEPLOY-PULL-RETRY attempt=\\$attempt/3", deploy)
        self.assertIn("sleep 20", deploy)
        self.assertIn("sleep 40", deploy)
        self.assertIn("advisory deploy-host-pull-inspect-rmi-failed", deploy)
        # inspect/rmi stay outside the retry loop.
        self.assertLess(deploy.index("done"), deploy.index("docker image inspect"))

    def test_cleanup_step_always_runs_and_verifies_absence(self):
        cleanup = step_block(self.text, "Delete ACR tag and verify removal")
        self.assertIn("if: always()", cleanup)
        # ACR personal: registry v2 delete only accepts a digest (tag DELETE
        # returns 400 DIGEST_INVALID — verified against the live registry).
        self.assertIn("-X DELETE -H \"Authorization: Bearer $token\"", cleanup)
        self.assertIn('"https://$ACR_REGISTRY/v2/$repo/manifests/$digest")', cleanup)
        # Read-back proof: the tag must be gone, verbatim "no such manifest".
        self.assertIn('grep -q \'no such manifest\'', cleanup)
        self.assertIn("advisory cleanup-verify-tag-still-exists", cleanup)
        self.assertIn("advisory cleanup-verify-inconclusive", cleanup)
        # gate-hub#2459: cleanup is advisory — a failed cleanup records
        # 'failed' in the receipt's cleanup field, emits the advisory warning
        # and exits 0; it never fails the job or the verdict.
        self.assertIn("::warning::RUNNER-ARTIFACT-CANARY-ACR-ADVISORY reason=acr-cleanup-failed", cleanup)
        self.assertIn('printf \'%s\' \'failed\' > "$RUNNER_TEMP/canary-cleanup-status"', cleanup)
        self.assertNotIn("RUNNER-ARTIFACT-CANARY-FAIL", cleanup)
        self.assertNotIn("exit 1", cleanup)
        self.assertNotIn("canary-failure-reason", cleanup)
        # Honest result recording: deleted / failed / skipped all reachable.
        self.assertIn("set_status deleted", cleanup)
        self.assertIn("set_status skipped", cleanup)

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
            'verdict = "pass" if (identity_ok and push_ok and local_ok and local_pull_ok) else "fail"',
            receipt,
        )
        # gate-hub#2459: the ACR deploy/cleanup conclusions are advisory and
        # must not appear anywhere in the verdict computation; local_pull_ok
        # derives from the local-pull status file.
        self.assertNotIn("deploy_ok", receipt)
        self.assertNotIn("cleanup_ok", receipt)
        self.assertIn('local_pull_ok = local_pull_status == "pass"', receipt)
        # Local push/read-back failure is a hard gate with its own reason;
        # the receipt re-validates the digest shape itself.
        self.assertIn('failure_reason = "local-push-failed" if not local_ok else "unknown-step-failure"', receipt)
        self.assertIn('re.fullmatch(r"sha256:[0-9a-f]{64}", local_digest)', receipt)
        # Contract object: status + repo_digests, digest null when invalid.
        self.assertIn('"local_digest": local_digest if local_ok else None', receipt)
        self.assertIn('"status": local_pull_status', receipt)
        self.assertIn('"repo_digests": json.loads(read_file("canary-local-pull-digests") or "[]")', receipt)

    def test_failure_marker_is_emitted_and_job_fails(self):
        # Hard-gate steps only: identity, push, local digest read-back and the
        # local pull (gate-hub#2459). The ACR deploy/cleanup legs are advisory
        # and must not carry the error marker.
        for step_name in ("Record runner identity and enforce engine contract",
                          "Build and push probe image to ACR",
                          "Read back local registry digest",
                          "Pull probe image from local registry on deploy host"):
            block = step_block(self.text, step_name)
            self.assertIn("RUNNER-ARTIFACT-CANARY-FAIL reason=", block, step_name)
            self.assertIn("exit 1", block, step_name)
        for advisory_step in ("Pull, inspect and remove probe image on deploy host",
                              "Delete ACR tag and verify removal"):
            block = step_block(self.text, advisory_step)
            self.assertNotIn("RUNNER-ARTIFACT-CANARY-FAIL", block, advisory_step)

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
