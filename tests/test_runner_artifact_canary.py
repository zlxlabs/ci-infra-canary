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
        self.assertIn("LOCAL_REGISTRY='' PUSH_MAX_ATTEMPTS=1", push)
        self.assertIn("FROM scratch", push)
        self.assertIn("password-stdin", push)

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
            'verdict = "pass" if (identity_ok and push_ok and deploy_ok and cleanup_ok) else "fail"',
            receipt,
        )

    def test_failure_marker_is_emitted_and_job_fails(self):
        for step_name in ("Record runner identity and enforce engine contract",
                          "Build and push probe image to ACR",
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
        self.assertGreaterEqual(len(uses), 3)
        for use in uses:
            self.assertRegex(use, r"^[^@]+@[0-9a-f]{40}$", use)

    def test_only_shared_secrets_are_used(self):
        used = sorted(set(re.findall(r"secrets\.([A-Z_]+)", self.text)))
        self.assertEqual(used, ["ACR_PASSWORD", "ACR_USERNAME", "KNOWN_HOSTS",
                                "SSH_DEPLOY_KEY", "TS_AUTHKEY"])


if __name__ == "__main__":
    unittest.main()
