#!/usr/bin/env python3
"""
Extract per-epoch summary blocks from route2_main_clean training log
and write a single condensed log with one block per epoch.
"""
import re
import sys
from pathlib import Path


def main():
    log_path = Path(r"c:\Users\eaad0\Desktop\route2_main_clean_20260314_043639.log")
    out_path = log_path.parent / (log_path.stem + "_epoch_summary.log")

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # Find header: everything before first "E1/30 train"
    header_end = 0
    for i, line in enumerate(lines):
        if re.match(r"E1/30 train:\s+\d+%", line):
            header_end = i
            break

    header = lines[:header_end]

    # Find each "  [HH:MM:SS] Epoch  N/30" line and the block until "  Backbone:" (inclusive)
    epoch_block_start = re.compile(r"^\s+\[\d+:\d+:\d+\] Epoch\s+\d+/30\b")
    backbone_line = re.compile(r"^\s+Backbone:")

    blocks = []
    i = header_end
    while i < len(lines):
        if epoch_block_start.match(lines[i]):
            block = [lines[i]]
            i += 1
            while i < len(lines) and not (lines[i].strip() and lines[i].startswith("E") and re.match(r"E\d+/30 train:", lines[i])):
                block.append(lines[i])
                if backbone_line.match(lines[i]):
                    i += 1
                    break
                i += 1
            blocks.append("".join(block))
            continue
        i += 1

    # Build output: header + separator + each epoch block
    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(header)
        f.write("\n")
        f.write("=" * 80 + "\n")
        f.write("Per-epoch summaries (detailed info for each epoch)\n")
        f.write("=" * 80 + "\n\n")
        for b in blocks:
            f.write(b)
            if not b.endswith("\n\n"):
                f.write("\n")

    print(f"Written {len(blocks)} epoch summaries to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
