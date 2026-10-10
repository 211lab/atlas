#!/usr/bin/env python3
"""Audit every Mermaid diagram in the repo for the element limit.

Rule (AGENTS.md, Conventions): a diagram stays at 5 elements or fewer.
Labels and connections do not count toward the limit.

Elements are nodes in flowcharts and participants in sequence diagrams.
The audit counts bracketed node definitions, bare node ids on edge lines
(with edge labels and node shapes stripped), and sequence-diagram
participants. Edge artifacts such as `--` and `-.-` are not elements.

Usage: python3 scripts/audit_diagrams.py   # exits 1 if any diagram is over
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 5

KEYWORDS = {
    "graph", "flowchart", "TD", "LR", "RL", "TB", "BT", "subgraph", "end",
    "direction", "sequenceDiagram", "participant", "autonumber",
    "activate", "deactivate",
}


def is_artifact(token: str) -> bool:
    return all(char in "-.=~>" for char in token)


def count_elements(block: str) -> set[str]:
    nodes: set[str] = set()
    if "sequenceDiagram" in block:
        return set(re.findall(r"participant\s+(\w+)", block))
    nodes |= set(re.findall(r"(\b[A-Za-z0-9_\-.]+)\s*(?:\[|\{|\()", block))
    for line in block.splitlines():
        if not any(edge in line for edge in ("-->", "---", "-.->", "==>")):
            continue
        line = re.sub(r"\|[^|]*\|", "", line)
        line = re.sub(r"(?:\[|\{|\()[^\]\})]*(?:\]|\}|\))", "", line)
        for token in re.findall(r"[A-Za-z0-9_\-.]+", line):
            if token not in KEYWORDS and not is_artifact(token):
                nodes.add(token)
    return nodes


def main() -> int:
    over: list[tuple[Path, int, int]] = []
    total = 0
    for md in sorted(ROOT.rglob("*.md")):
        if ".git" in md.parts or "node_modules" in md.parts:
            continue
        text = md.read_text(encoding="utf-8")
        for index, block in enumerate(
            re.findall(r"```mermaid\n(.*?)```", text, re.S), 1
        ):
            total += 1
            count = len(count_elements(block))
            if count > LIMIT:
                over.append((md.relative_to(ROOT), index, count))
    for path, index, count in over:
        print(f"OVER {path} block {index}: {count} elements (limit {LIMIT})")
    print(f"{total} diagrams audited, {len(over)} over the limit")
    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main())
