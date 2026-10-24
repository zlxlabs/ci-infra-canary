import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github/workflows/release-receipt.yml"
GATE = ROOT / ".github/workflows/gate.yml"
SCHEMA = "gate-hub.release-receipt-request.v2"
ANCHOR = "RELEASE-RECEIPT-REQUEST-INVALID"
FP = "012345abcdef"
HOST_BOTH, HOST_CI = "ci-01", "ci-03"
CI_LABEL_BOTH = f"canary-{FP}-{HOST_BOTH}-ci"
REVIEW_LABEL_BOTH = f"canary-{FP}-{HOST_BOTH}-review"
CI_LABEL_CI = f"canary-{FP}-{HOST_CI}-ci"
LEGACY_LABEL_BOTH = f"canary-{FP}-{HOST_BOTH}"


def _extract_reader_script(workflow: str) -> str:
    lines = workflow.splitlines()
    start = next(i for i, line in enumerate(lines) if line == "        run: |")
    script = []
    for line in lines[start + 1 :]:
        if line and not line.startswith("          "):
            break
        script.append(line[10:] if line else "")
    return "\n".join(script)


def _payload(**overrides):
    data = {
        "schema": SCHEMA,
        "roll_id": "roll-1",
        "fingerprint": FP,
        "host": HOST_BOTH,
        "ci_label": CI_LABEL_BOTH,
        "review_label": REVIEW_LABEL_BOTH,
    }
    data.update(overrides)
    return json.dumps(data, separators=(",", ":"))


class ReleaseReceiptWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text()
        self.gate = GATE.read_text()

    def test_workflow_name_is_release_receipt_not_gate(self):
        self.assertRegex(self.workflow, r"(?m)^name:\s*release-receipt\s*$")
        self.assertNotRegex(self.workflow, r"(?m)^name:\s*gate\s*$")

    def test_uses_gate_v2_tag_not_main(self):
        self.assertRegex(
            self.workflow,
            r"(?m)^\s*uses:\s+zlxlabs/gate/\.github/workflows/gate-v2\.yml@v2\s*$",
        )
        self.assertNotRegex(self.workflow, r"gate-v2\.yml@main")

    def test_reader_paths_if_outputs_and_original_gate_pin(self):
        wf = self.workflow
        self.assertIn("runs-on: ubuntu-latest", wf)
        self.assertNotIn("self-hosted", wf)
        self.assertIn("actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683", wf)
        self.assertIn("ref: ${{ github.event.pull_request.head.sha }}", wf)
        self.assertIn("persist-credentials: false", wf)
        self.assertRegex(
            wf,
            r"(?ms)^on:\n  pull_request:\n    types: \[opened, synchronize, reopened\]\n"
            r"    paths:\n      - '\.ci-release-receipt'\n",
        )
        self.assertNotIn("paths-ignore:", wf)
        self.assertIn("startsWith(github.head_ref, 'release-receipt/')", wf)
        self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", wf)
        self.assertIn("github.event.pull_request.draft == false", wf)
        self.assertIn("extra_runner_label_ci: ${{ needs.reader.outputs.ci_label }}", wf)
        self.assertIn("extra_runner_label_review: ${{ needs.reader.outputs.review_label }}", wf)
        self.assertNotIn("concurrency:", wf)
        self.assertIn(ANCHOR, wf)
        self.assertRegex(self.gate, r"(?ms)paths-ignore:.*?- '\.ci-release-receipt'")
        self.assertRegex(
            self.gate,
            r"(?m)^\s*uses:\s+zlxlabs/gate/\.github/workflows/gate-v2\.yml@main\s*$",
        )


class ReleaseReceiptReaderScriptTests(unittest.TestCase):
    def setUp(self):
        self.script = _extract_reader_script(WORKFLOW.read_text())

    def _run(self, payload=None, *, missing=False):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            if not missing:
                (tmp_path / ".ci-release-receipt").write_text(payload, encoding="utf-8")
            output = tmp_path / "github_output"
            output.write_bytes(b"")
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", self.script],
                cwd=tmp_path,
                env=os.environ | {"GITHUB_OUTPUT": str(output)},
                capture_output=True,
                text=True,
            )
            return result, output.read_bytes()

    def test_valid_both_labels_write_exact_distinct_bytes(self):
        result, out = self._run(_payload())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            out,
            f"ci_label={CI_LABEL_BOTH}\nreview_label={REVIEW_LABEL_BOTH}\n".encode(),
        )

    def test_valid_ci_only_writes_empty_review_verbatim(self):
        result, out = self._run(_payload(host=HOST_CI, ci_label=CI_LABEL_CI, review_label=""))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(out, f"ci_label={CI_LABEL_CI}\nreview_label=\n".encode())

    def test_invalid_inputs_fail_loud_without_label_lines(self):
        cases = {
            "schema": _payload(schema="nope"),
            "schema-v1-rejected": _payload(schema="gate-hub.release-receipt-request.v1"),
            "fingerprint": _payload(fingerprint="ABCDEF012345"),
            "legacy-suffixless-label": _payload(
                ci_label=LEGACY_LABEL_BOTH, review_label=LEGACY_LABEL_BOTH
            ),
            "suffix-swapped": _payload(
                ci_label=f"canary-{FP}-{HOST_BOTH}-review",
                review_label=f"canary-{FP}-{HOST_BOTH}-ci",
            ),
            "label-mismatch": _payload(ci_label="canary-nope"),
            "labels-empty": _payload(ci_label="", review_label=""),
            "not-json": "{not json",
            "missing": None,
        }
        for name, payload in cases.items():
            with self.subTest(name=name):
                result, out = self._run(payload, missing=payload is None)
                combined = result.stdout + "\n" + result.stderr
                self.assertNotEqual(result.returncode, 0, combined)
                self.assertTrue(
                    any(line.startswith(ANCHOR) for line in combined.splitlines()),
                    combined,
                )
                self.assertNotIn(b"ci_label=", out)
                self.assertNotIn(b"review_label=", out)


if __name__ == "__main__":
    unittest.main()
