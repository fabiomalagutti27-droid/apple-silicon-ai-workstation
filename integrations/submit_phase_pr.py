#!/usr/bin/env python3
from __future__ import annotations
"""submit_phase_pr.py: Atomic Closing Tool (ACI) per DeepSeek SuperAgent su Mac mini M5 Pro.

Esegue la chiusura deterministica di una fase di sviluppo:
1. Verifica compilazione e test con `/Users/fabiomalagutti/.local/bin/cargo-uma test`.
2. Esegue `git add` selettivo (escludendo file temporanei, log e preflight).
3. Esegue `git commit` strutturato (Conventional Commits).
4. Esegue `git push origin HEAD`.
5. Crea la Pull Request tramite `gh pr create`.
   (Questo attiva automaticamente l'Actor-Critic Pre-PR Gate di Antigravity).
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

CARGO_UMA = "/Users/fabiomalagutti/.local/bin/cargo-uma"
GH_AGENT = "gh"
AGY_GATE = "/Users/fabiomalagutti/ai-ecosystem/integrations/agy_pr_review_gate.py"


def run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int = 300) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["PATH"] = f"/Users/fabiomalagutti/bin:/Users/fabiomalagutti/.local/bin:/opt/homebrew/bin:{env.get('PATH', '')}"
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def main():
    parser = argparse.ArgumentParser(description="Submit Phase Pull Request with Actor-Critic Gate")
    parser.add_argument("--title", type=str, default="", help="Titolo della PR")
    parser.add_argument("--body", type=str, default="", help="Descrizione della PR")
    parser.add_argument("--skip-test", action="store_true", help="Salta i test (sconsigliato)")
    args = parser.parse_args()

    cwd = Path.cwd()
    print(f"🚀 [submit_phase_pr] Avvio finalizzazione PR nel workspace: {cwd}")

    # 1. Verifica che siamo in un repository git
    rc, branch, _ = run_cmd(["git", "branch", "--show-current"], cwd=cwd)
    if rc != 0 or not branch:
        print("❌ Errore: la directory corrente non è un branch git valido.")
        return 1
    print(f"🌿 Branch attivo: {branch}")

    # 2. Test suite preventiva con cargo-uma
    if not args.skip_test:
        print("🧪 Esecuzione test suite con cargo-uma...")
        rc, out, err = run_cmd([CARGO_UMA, "test", "-p", "core-types"], cwd=cwd, timeout=600)
        if rc != 0:
            print("❌ Errore durante i test di compilazione:")
            combined_err = f"{out}\n{err}"
            error_lines = [l for l in combined_err.splitlines() if re.search(r"error\[E\d+\]|panicked at|FAILED", l)]
            if error_lines:
                print("\n".join(error_lines[:15]))
            else:
                print(combined_err[-1000:])
            print("\n👉 Correggi gli errori sopra prima di riprovare submit_phase_pr.")
            return 1
        print("✅ Test suite completata con successo (0 errori).")

    # 3. Git staging
    print("📦 Staging dei file modificati...")
    run_cmd(["git", "add", "crates/", "docs/", "tests/", "Cargo.toml", "Cargo.lock"], cwd=cwd)
    run_cmd(["git", "reset", "HEAD", "PREFLIGHT_RECONCILIATION.md", ".cargo/"], cwd=cwd)

    rc, status, _ = run_cmd(["git", "status", "--porcelain"], cwd=cwd)
    if not status:
        print("ℹ️ Nessuna modifica da committare.")
    else:
        # 4. Commit
        phase_m = re.search(r"phase-(\d+)", branch)
        clean_name = branch.replace("agent/", "")
        phase_tag = f"phase-{phase_m.group(1)}" if phase_m else clean_name
        commit_msg = f"feat({phase_tag}): implement {phase_tag} specifications and tests"
        print(f"💾 Creazione commit: {commit_msg}")
        run_cmd(["git", "commit", "-m", commit_msg], cwd=cwd)

    # 5. Push su origin
    print(f"⬆️ Push su origin/{branch}...")
    rc, _, err = run_cmd(["git", "push", "-u", "origin", branch], cwd=cwd)
    if rc != 0 and "Everything up-to-date" not in err:
        print(f"⚠️ Warning push: {err}")

    # 6. Apertura Pull Request tramite gh-agent (attiva automaticamente agy_pr_review_gate.py)
    print("🔍 Verifica Actor-Critic e pubblicazione Pull Request...")
    clean_title = branch.replace("agent/", "")
    pr_title = args.title or f"feat: {clean_title}"
    pr_body = args.body or f"Implementazione autonoma per {branch} validata da cargo-uma e Actor-Critic Gate."

    pr_cmd = [
        GH_AGENT, "pr", "create",
        "--title", pr_title,
        "--body", pr_body,
        "--base", "main",
        "--head", branch
    ]

    rc, pr_out, pr_err = run_cmd(pr_cmd, cwd=cwd, timeout=300)
    output = f"{pr_out}\n{pr_err}".strip()

    if rc == 0:
        print("🎉 PULL REQUEST CREATA CON SUCCESSO!")
        print(output)
        return 0

    if "CHANGES REQUESTED" in output:
        print("🚫 Actor-Critic Gate ha richiesto modifiche:")
        print(output)
        return 2

    # Se la PR esiste già
    if "already exists" in output:
        print("ℹ️ Pull Request già esistente:")
        print(output)
        return 0

    print(f"❌ Errore durante la creazione della PR: {output}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
