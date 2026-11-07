#!/usr/bin/env python3
"""
log_pruner.py - Densitomicro-filtro Deterministico per Log di Compilazione ed Errori
Filtra chirurgicamente gli output prolissi di build e test (Rust/Cargo, Python/pytest, Node/TypeScript),
estraendo solo gli errori critici, le coordinate di riga e i traceback pertinenti.
Riduce fino al 90% i token di contesto inviati agli agenti LLM (SuperAgent, Goose, Copilot) in <2ms.
"""

import sys
import re
from typing import List, Optional

RUST_DIAGNOSTIC_RE = re.compile(
    r"((?:error|warning)\[E\d+\]:.*?\n\s+-->\s+.*?\n(?:\s+│.*?\n)*)",
    re.MULTILINE
)
RUST_PANIC_RE = re.compile(
    r"(thread '.*?' panicked at .*?\n(?:stack backtrace:\n.*?\n\s*0:.*?)?)",
    re.DOTALL
)
PY_TRACEBACK_RE = re.compile(
    r"(Traceback \(most recent call last\):.*?\n\w+(?:Error|Exception): .*?)(?=\n\n|\Z)",
    re.DOTALL
)
TS_ERROR_RE = re.compile(
    r"(.*?\(\d+,\d+\): error TS\d+: .*?)(?=\n|$)",
    re.MULTILINE
)

def prune_compiler_log(raw_log: str, max_lines: int = 100) -> str:
    """
    Analizza il log grezzo e produce una versione ultra-sintetica focalizzata sugli errori.
    """
    if not raw_log or not raw_log.strip():
        return ""

    rust_errors = RUST_DIAGNOSTIC_RE.findall(raw_log)
    rust_panics = RUST_PANIC_RE.findall(raw_log)
    py_errors = PY_TRACEBACK_RE.findall(raw_log)
    ts_errors = TS_ERROR_RE.findall(raw_log)

    total_detected = len(rust_errors) + len(rust_panics) + len(py_errors) + len(ts_errors)

    if total_detected > 0:
        summary_blocks: List[str] = [
            f"/* [LOG-PRUNER: {total_detected} ERRORI CHIAVE ESTRATTI CHIRURGICAMENTE] */\n"
        ]

        if rust_errors:
            summary_blocks.append("--- RUST DIAGNOSTICS ---")
            summary_blocks.extend(rust_errors[:12])

        if rust_panics:
            summary_blocks.append("--- RUST PANICS ---")
            summary_blocks.extend(rust_panics[:3])

        if py_errors:
            summary_blocks.append("--- PYTHON TRACEBACKS ---")
            summary_blocks.extend(py_errors[:5])

        if ts_errors:
            summary_blocks.append("--- TYPESCRIPT DIAGNOSTICS ---")
            summary_blocks.extend(ts_errors[:10])

        return "\n\n".join(summary_blocks)

    # Se non vengono rilevate firme note, filtra le righe innocue di build
    filtered_lines = []
    noise_prefixes = (
        "   Compiling ", "    Checking ", "    Finished ", "    Updating ",
        "    Locking ", "    Downloaded ", "      Fresh ", "      Running "
    )
    for line in raw_log.splitlines():
        if not line.startswith(noise_prefixes) and line.strip():
            filtered_lines.append(line)

    if len(filtered_lines) > max_lines:
        tail = filtered_lines[-max_lines:]
        return f"/* [LOG-PRUNER: Log compresso da {len(filtered_lines)} a {len(tail)} righe rilevanti] */\n\n" + "\n".join(tail)

    return "\n".join(filtered_lines)


def main():
    if len(sys.argv) > 1 and sys.argv[1] not in ["-", "--stdin"]:
        try:
            with open(sys.argv[1], "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            sys.stderr.write(f"Errore lettura file: {e}\n")
            sys.exit(1)
    else:
        content = sys.stdin.read()

    pruned = prune_compiler_log(content)
    sys.stdout.write(pruned + "\n")


if __name__ == "__main__":
    main()
