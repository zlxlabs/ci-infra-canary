"""执行真实判定脚本（subprocess），喂字节级真实日志切片 fixture。

正样本取自本仓 PR #66 quality job 128658884417 日志，负样本取自 gate 仓
quality job 128486678343 日志（无 Emit 步骤的历史 gate run）；派生用例由
正样本文本变换得出。每个用例断言退出码与 stdout 的 reason。
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).parents[1]
SCRIPT = REPO / "scripts" / "verify_tested_evidence.py"
FIXTURES = REPO / "tests" / "fixtures" / "tested_evidence"
WANT_HEAD = "f6e9913bbf4e179b3562392eb76186056ed28370"
MERGE_SHA = "2de46fd3ae9cb957a4ef9042e108288f1a994d17"
FAKE_HEAD = "a" * 40
EVIDENCE = f"GATE-TESTED-EVIDENCE-V1 head_sha={WANT_HEAD} merge_sha={MERGE_SHA} mode=pytest"


class VerifyTestedEvidenceScriptTests(unittest.TestCase):
    def run_script(self, log_text, want_head=WANT_HEAD):
        with tempfile.NamedTemporaryFile("w", suffix=".log", encoding="utf-8", delete=False) as fh:
            fh.write(log_text)
            path = fh.name
        try:
            return subprocess.run(
                [sys.executable, str(SCRIPT), path, want_head],
                capture_output=True,
                text=True,
            )
        finally:
            Path(path).unlink(missing_ok=True)

    def positive(self):
        return (FIXTURES / "quality-ok.log").read_text(encoding="utf-8")

    def negative(self):
        return (FIXTURES / "quality-no-emit.log").read_text(encoding="utf-8")

    def test_real_quality_log_slice_passes(self):
        proc = self.run_script(self.positive())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(f"TESTED-EVIDENCE-CHECK ok head_sha={WANT_HEAD} mode=pytest", proc.stdout)

    def test_real_log_without_emit_region_fails(self):
        proc = self.run_script(self.negative())
        self.assertEqual(proc.returncode, 1)
        self.assertIn("TESTED-EVIDENCE-CHECK reason=emit_region_missing", proc.stdout)

    def test_zero_evidence_lines_fails(self):
        text = self.positive().replace(
            f"GATE-TESTED-EVIDENCE-V1 head_sha={WANT_HEAD}",
            f"GATE-TESTED-EVIDENCE-X head_sha={WANT_HEAD}",
        )
        proc = self.run_script(text)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("TESTED-EVIDENCE-CHECK reason=evidence_missing", proc.stdout)

    def test_duplicate_evidence_lines_fail(self):
        text = self.positive().replace(EVIDENCE, EVIDENCE + "\n" + EVIDENCE)
        proc = self.run_script(text)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("TESTED-EVIDENCE-CHECK reason=evidence_duplicate count=2", proc.stdout)

    def test_wrong_head_sha_fails(self):
        text = self.positive().replace(
            f"head_sha={WANT_HEAD} merge_sha", f"head_sha={FAKE_HEAD} merge_sha"
        )
        proc = self.run_script(text)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("TESTED-EVIDENCE-CHECK reason=head_sha_mismatch", proc.stdout)
        self.assertIn(f"got={FAKE_HEAD}", proc.stdout)

    def test_mode_entry_fails(self):
        text = self.positive().replace("mode=pytest", "mode=entry")
        proc = self.run_script(text)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("TESTED-EVIDENCE-CHECK reason=mode_mismatch got=entry", proc.stdout)

    def test_emit_failed_marker_inside_region_fails(self):
        warned = (
            "2026-11-08T07:04:48.9999999Z ::warning::GATE-TESTED-EVIDENCE-EMIT-FAILED"
        )
        text = self.positive().replace(EVIDENCE + "\n", EVIDENCE + "\n" + warned + "\n")
        proc = self.run_script(text)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("TESTED-EVIDENCE-CHECK reason=emit_failed_in_region", proc.stdout)

    def test_forged_evidence_outside_region_is_ignored(self):
        forged = (
            f"2026-11-08T07:04:48.0000000Z GATE-TESTED-EVIDENCE-V1 head_sha={FAKE_HEAD} "
            f"merge_sha={'b' * 40} mode=pytest"
        )
        proc = self.run_script(forged + "\n" + self.positive())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(f"TESTED-EVIDENCE-CHECK ok head_sha={WANT_HEAD} mode=pytest", proc.stdout)

    def test_crlf_line_endings_still_pass(self):
        proc = self.run_script(self.positive().replace("\n", "\r\n"))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("TESTED-EVIDENCE-CHECK ok head_sha=", proc.stdout)

    def test_leading_bom_still_pass(self):
        proc = self.run_script("﻿" + self.positive())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("TESTED-EVIDENCE-CHECK ok head_sha=", proc.stdout)


if __name__ == "__main__":
    unittest.main()
