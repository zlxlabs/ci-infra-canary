import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "nonroot-pilot-probe.yml"

# Byte-for-byte the canary label regex the gate-hub launcher enforces on slot
# activation (gate-hub runner/run-ephemeral-runner.sh:1993). The probe's
# validate-inputs must accept exactly the label shape the launcher itself
# accepts — one shared format, not two drift-prone ones.
LAUNCHER_CANARY_LABEL_REGEX = r"^canary-[0-9a-f]{12}-[a-z0-9][a-z0-9-]*$"

# Phase-1 routing invariant (gate-hub#2384 design §5.2): the pilot slot
# registers ONLY its canary label, so pilot jobs must require exactly
# self-hosted + linux + the validated label and never the lane label `ci`.
PILOT_RUNS_ON = 'runs-on: [self-hosted, linux, "${{ needs.validate-inputs.outputs.canary_label }}"]'

# One verdict line per matrix item; P11 is observational (design §5.2) and
# must never fail the run.
VERDICT_ITEMS = ("P1", "P2", "P4", "P5", "P6", "P7", "P8", "P9", "P11", "P7HIT", "P9HIT")

GRADLE_WRAPPER_VERSION = "8.10.2"


class NonrootPilotProbeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github" / "workflows" / "nonroot-pilot-probe.yml").read_text()

    def _job_block(self, job_name):
        lines = self.workflow.splitlines()
        start = next(i for i, line in enumerate(lines) if line == f"  {job_name}:")
        end = next(
            (
                i
                for i, line in enumerate(lines[start + 1:], start=start + 1)
                if line.startswith("  ") and not line.startswith("    ") and line.endswith(":")
            ),
            len(lines),
        )
        return "\n".join(lines[start:end])

    def test_manual_dispatch_is_the_only_trigger(self):
        # Phase-1 probe is operator-dispatched only (design §5.2): no schedule,
        # no PR/push wiring, so the pilot slot can never pick up real traffic
        # through this file.
        lines = self.workflow.splitlines()
        on_idx = next(i for i, line in enumerate(lines) if line == "on:")
        end = next(
            (
                i
                for i, line in enumerate(lines[on_idx + 1:], start=on_idx + 1)
                if line and not line.startswith(" ")
            ),
            len(lines),
        )
        trigger_block = "\n".join(lines[on_idx + 1:end])
        self.assertIn("workflow_dispatch:", trigger_block)
        for forbidden in ("push:", "pull_request:", "schedule:", "workflow_run:", "repository_dispatch:", "workflow_call:"):
            self.assertNotIn(forbidden, trigger_block)

    def test_read_only_permissions_and_reentry_guard(self):
        self.assertIn("permissions:\n  contents: read", self.workflow)
        self.assertIn("group: nonroot-pilot-probe-${{ inputs.canary_label }}", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)

    def test_pilot_jobs_run_on_canary_label_without_lane_label(self):
        # Both pilot jobs (probe + cross-job hit) must declare EXACTLY the
        # canary runs-on; a bare `ci` label anywhere in a runs-on would leak
        # probe jobs onto real traffic slots.
        self.assertEqual(self.workflow.count(PILOT_RUNS_ON), 2)
        self.assertNotRegex(self.workflow, r"runs-on:.*\bci\b")
        self.assertIn("runs-on: ubuntu-latest", self._job_block("validate-inputs"))

    def test_canary_label_regex_is_byte_identical_to_launcher(self):
        # The workflow carries the launcher's regex verbatim (bash =~ form);
        # any drift between the two copies would let this probe dispatch a
        # label the launcher itself would refuse at slot activation.
        self.assertIn(f"[[ \"$CANARY_LABEL\" =~ {LAUNCHER_CANARY_LABEL_REGEX} ]]", self.workflow)

    def test_expected_uid_choice_is_restricted_to_pilot_and_rollback(self):
        block = self.workflow[self.workflow.index("expected_uid:") :]
        block = block[: block.index("permissions:")]
        self.assertIn('default: "1000"', block)
        options = re.findall(r'^\s+- "([^"]*)"$', block, re.MULTILINE)
        # Exactly the pilot run (1000) and the P12 rollback drill (0); any
        # other uid semantics would silently widen the probe's claims.
        self.assertEqual(sorted(options), ["0", "1000"])

    def test_third_party_actions_are_pinned_to_full_shas(self):
        # Constraint: every third-party action is pinned to a 40-hex commit
        # SHA (same practice as the rest of this repo); `uses:` values without
        # a `./` prefix must carry the full SHA, never a movable tag/branch.
        uses = re.findall(r"uses:\s*(\S+)", self.workflow)
        self.assertTrue(uses)
        for ref in uses:
            if ref.startswith("./"):
                continue
            m = re.fullmatch(r"([^@]+)@([0-9a-f]{40})", ref)
            self.assertIsNotNone(m, f"unpinned third-party action: {ref}")
            self.assertNotRegex(ref, r"@main$|@master$|@v\d")

    def test_every_matrix_item_prints_one_verdict_marker(self):
        for item in VERDICT_ITEMS:
            self.assertRegex(self.workflow, rf"NONROOT-PROBE-V1 item={item} status=(pass|fail|info)")
        self.assertIn("status=info exit_code=$rc", self.workflow)

    def test_p11_is_observational_and_never_fails_the_run(self):
        block = self._job_block("pilot-probe")
        start = block.index("- name: P11 unprivileged user namespace (observational)")
        step = block[start:]
        self.assertIn("status=info", step)
        self.assertNotIn("exit 1", step)
        self.assertNotRegex(step, r"fail \(")

    def test_pilot_job_timeouts_are_within_budget(self):
        # Card constraint: every pilot job declares timeout-minutes <= 20 so a
        # wedged probe cannot hold the single pilot slot hostage.
        for job_name in ("validate-inputs", "pilot-probe", "cache-hit-check"):
            m = re.search(rf"^  {job_name}:\n(?:.*\n)*?    timeout-minutes: (\d+)$", self.workflow, re.MULTILINE)
            self.assertIsNotNone(m, f"{job_name} missing timeout-minutes")
            self.assertLessEqual(int(m.group(1)), 20)

    def test_p4_encodes_both_uid_semantics(self):
        # expected_uid=1000: the 0555 write must fail with EACCES (the
        # gate-hub#2384 fix). expected_uid=0 (rollback drill P12): root must
        # succeed. Both branches asserted in the step.
        self.assertIn('[ "$EXPECTED_UID" = "1000" ]', self.workflow)
        self.assertIn('"EACCES"', self.workflow)
        self.assertIn("root-write-should-succeed", self.workflow)

    def test_p2_uses_job_side_client_with_gate_v2_argv_shape(self):
        # gate-v2@v2 GATE_SOURCE_PREPARE_SCRIPT (gate-v2.yml:231-237) calls
        # the client with --repository/--commit/--deadline-epoch and judges the
        # stderr protocol line; the probe must reuse that exact argv shape and
        # the documented job-side client path.
        self.assertIn("client=/opt/gate-hub-cache/git/git-source-prepare", self.workflow)
        self.assertIn("--repository \"$PROBE_REPOSITORY\" --commit \"$PROBE_COMMIT\" --deadline-epoch \"$deadline\"", self.workflow)
        self.assertIn("grep -c '^GIT-SOURCE-PREPARE-V1 '", self.workflow)
        self.assertIn("GATE_HUB_SOURCE_PROXY_SOCK", self.workflow)

    def test_probe_does_not_consume_secrets(self):
        # The probe needs no credentials: the job-side source client carries
        # none (design §3.3) and checkout uses the default token without
        # persisting it. A secrets reference appearing here would be a new
        # attack surface on a canary slot.
        self.assertNotIn("secrets.", self.workflow)

    def test_gradle_fixture_pins_wrapper_version_and_gradlew_is_executable(self):
        props = (ROOT / "probe" / "nonroot" / "gradle" / "gradle" / "wrapper" / "gradle-wrapper.properties").read_text()
        self.assertIn(f"gradle-{GRADLE_WRAPPER_VERSION}-bin.zip", props)
        gradlew = ROOT / "probe" / "nonroot" / "gradle" / "gradlew"
        self.assertTrue(gradlew.stat().st_mode & 0o111, "gradlew must keep its executable bit in git")
        wrapper_jar = ROOT / "probe" / "nonroot" / "gradle" / "gradle" / "wrapper" / "gradle-wrapper.jar"
        self.assertTrue(wrapper_jar.is_file())
        # P7 judges the shared-mount landing of exactly this dist version;
        # the cross-job hit check must look for the same version directory.
        self.assertIn(f"gradle-{GRADLE_WRAPPER_VERSION}-bin", self.workflow)
        self.assertIn("./gradlew --version", self.workflow)

    def test_p8_targets_the_baked_node22_version(self):
        # The runner image bakes node 22.23.3 into the toolcache (gate-hub
        # runner/Dockerfile toolcache self-check). setup-node must request that
        # exact version so the baked-hit assertion (unchanged directory mtime)
        # actually tests the warm path, not a coincidental re-download.
        self.assertIn("node-version: 22.23.3", self.workflow)
        self.assertIn("P8_BAKED_MTIME", self.workflow)
        self.assertIn("baked_hit=1", self.workflow)


if __name__ == "__main__":
    unittest.main()
