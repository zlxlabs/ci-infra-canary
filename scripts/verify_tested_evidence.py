#!/usr/bin/env python3
"""Strict acceptance check of GATE-TESTED-EVIDENCE-V1 in one `gate / quality` job log.

usage: verify_tested_evidence.py <job.log> <expected_head_sha>

语义（照抄 gate 仓参考实现 verify_evidence.py，mode 固定为 pytest、merge 只验格式）：
按 \\n 分行、去单个尾部 \\r、剥可选时间戳前缀、首行去 BOM；Emit 区间 = 唯一一行
等于 HEADER 的行起、其后第一个 `##[endgroup]` 之后、到下一个以 `##[group]Run `
开头的行之前。区间输出内须恰有一行完整匹配证据行格式，head_sha 等于期望值，
mode 等于 pytest，且区间内无 GATE-TESTED-EVIDENCE-EMIT-FAILED。

成功打印 `TESTED-EVIDENCE-CHECK ok head_sha=... mode=pytest` 并退出 0；
失败打印一行可 grep 的 `TESTED-EVIDENCE-CHECK reason=<枚举>` 并非零退出。
"""
import re
import sys

HEADER = "##[group]Run python3 - <<'PY' || echo \"::warning::GATE-TESTED-EVIDENCE-EMIT-FAILED\""
TS = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z ")
LINE = re.compile(r"GATE-TESTED-EVIDENCE-V1 head_sha=([0-9a-f]{40}) merge_sha=([0-9a-f]{40}) mode=(entry|pytest)")


def fail(reason, detail=""):
    print(f"TESTED-EVIDENCE-CHECK reason={reason}{f' {detail}' if detail else ''}")
    sys.exit(1)


def main(argv):
    if len(argv) != 3:
        print(f"usage: {argv[0]} <job.log> <expected_head_sha>", file=sys.stderr)
        return 2
    log_path, want_head = argv[1], argv[2]
    if not re.fullmatch(r"[0-9a-f]{40}", want_head):
        fail("bad_expected_head", f"want={want_head}")
    with open(log_path, "rb") as fh:
        raw_lines = fh.read().decode("utf-8").split("\n")
    # BOM 是文件级伪影：必须先于逐行时间戳剥离去掉，否则首行「BOM+时间戳」
    # 会让锚定的 TS.match 失败、时间戳残留（与参考实现的顺序差异，见报告偏差节）。
    raw_lines[0] = raw_lines[0].lstrip("\ufeff")
    lines = []
    for raw in raw_lines:
        if raw.endswith("\r"):
            raw = raw[:-1]
        m = TS.match(raw)
        lines.append(raw[m.end():] if m else raw)

    starts = [i for i, l in enumerate(lines) if l == HEADER]
    if len(starts) == 0:
        fail("emit_region_missing")
    if len(starts) > 1:
        fail("emit_region_ambiguous", f"count={len(starts)}")
    start = starts[0]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("##[group]Run ")), len(lines))
    region = lines[start:end]
    endgroup = next((i for i, l in enumerate(region) if l == "##[endgroup]"), None)
    if endgroup is None:
        fail("emit_region_unterminated")
    output = region[endgroup + 1:]
    hits = [m for m in (LINE.fullmatch(l) for l in output) if m]
    if any("GATE-TESTED-EVIDENCE-EMIT-FAILED" in l for l in output):
        fail("emit_failed_in_region")
    if len(hits) == 0:
        fail("evidence_missing")
    if len(hits) > 1:
        fail("evidence_duplicate", f"count={len(hits)}")
    hit = hits[0]
    if hit.group(1) != want_head:
        fail("head_sha_mismatch", f"got={hit.group(1)} want={want_head}")
    if hit.group(3) != "pytest":
        fail("mode_mismatch", f"got={hit.group(3)}")
    print(f"TESTED-EVIDENCE-CHECK ok head_sha={hit.group(1)} mode=pytest")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
