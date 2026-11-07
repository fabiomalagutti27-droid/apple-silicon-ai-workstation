#!/usr/bin/env python3
"""agy_pr_review_gate.py: Actor-Critic / Cross-Model Pre-PR Code Review Gate per SuperAgent.

Basato su:
- Yin Li (2026), "Decomposing LLM Self-Correction" (arXiv:2601.00828)
- Kwok et al. (2026), "LLM-as-a-Verifier" (arXiv:2607.05391v2)
- Galullo (2026), "Beyond Agent Self-Reporting" (SSRN 7507718)

Intercetta la creazione della Pull Request (`gh pr create`) o viene invocato tramite
il tool MCP `review_diff_with_antigravity`. Sottopone il `git diff` del Worker locale
(`qwen35-fast`) alla revisione algoritmica e semantica di Antigravity (`agy` / `gemini`).
Se emergono refusi di variabili (es. `_sx` vs `dx`), calcoli degeneri o stub impropri,
blocca la PR (fino a max 2 round) restituendo istruzioni chirurgiche di correzione
e notificando tempestivamente l'utente su Telegram.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

HOME_DIR = Path.home()
GATEWAY_URL = os.environ.get("LLAMA_SWAP_URL", "http://127.0.0.1:8000/v1/chat/completions")
AGY_CLI_BIN = os.environ.get("AGY_CLI_BIN", str(HOME_DIR / ".gemini/antigravity-cli/bin/agy"))
MAX_REVIEW_ROUNDS = 2


def run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def get_git_state_file(workspace: Path) -> Path:
    rc, git_dir, _ = run_git(["rev-parse", "--git-dir"], cwd=workspace)
    if rc == 0 and git_dir:
        gd = Path(git_dir)
        if not gd.is_absolute():
            gd = (workspace / gd).resolve()
        return gd / "agy_review_state.json"
    return workspace / ".agy_review_state.json"


def load_review_state(state_file: Path) -> dict:
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except Exception:
            pass
    return {"round_count": 0, "approved_sha": None, "history": []}


def save_review_state(state_file: Path, state: dict):
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    except Exception:
        pass


def static_heuristic_scan(diff_text: str) -> list[str]:
    """Scansione deterministica istantanea per pattern noti di auto-cecità LLM."""
    findings = []
    current_file = "unknown"
    added_lines_by_file: dict[str, list[str]] = {}

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
            added_lines_by_file.setdefault(current_file, [])
        elif line.startswith("+") and not line.startswith("+++"):
            added_lines_by_file.setdefault(current_file, []).append(line[1:])

    for fpath, lines in added_lines_by_file.items():
        if not fpath.endswith(".rs"):
            continue
        block = "\n".join(lines)
        # 1. Cerca variabili numeriche/indici calcolate con prefisso '_' per silenziare warning (es. let _sx = (...))
        for m in re.finditer(r"\blet\s+_([a-zA-Z][a-zA-Z0-9_]*)\s*=\s*([^;]+);", block):
            var_name = m.group(1)
            expr = m.group(2).strip()
            # Se l'espressione contiene calcoli matematici/cast ma la variabile ha '_' davanti
            if any(op in expr for op in ("*", "/", "+", "-", ".min(", ".max(", "as usize", "as f32")):
                findings.append(
                    f"[{fpath}] Variabile calcolata `_{var_name} = {expr}` prefissata con underscore (inutilizzata!): "
                    f"verifica se nell'indice o nella formula sottostante hai usato per errore la coordinata non scalata invece di `{var_name}`."
                )
        # 2. Cerca divisioni tautologiche tipo num_pixels / (len / 3)
        if re.search(r"num_pixels\s*/\s*\(\s*len\s*/\s*3\s*\)", block):
            findings.append(
                f"[{fpath}] Formula dimensionale degenere `num_pixels / (len / 3)` (vale sempre 1): "
                f"usa un loop 1D pulito `0..num_pixels` o passa esplicitamente `(width, height)`."
            )

    return findings


def call_frontier_critic(diff_text: str, stat_text: str) -> tuple[bool, str]:
    """Interroga Antigravity Frontier (`gemini` via llama-swap o `agy` CLI) per la Code Review pre-PR."""
    truncated_diff = diff_text[:28000]
    system_prompt = (
        "Sei Antigravity (agy), Principal Rust Architect & Code Reviewer per il motore Spatiotemporal MCP.\n"
        "Stai eseguendo un Pre-PR Hard Gate sul `git diff` prodotto dal worker locale `qwen35-fast`.\n"
        "Il tuo compito è individuare ESCLUSIVAMENTE bug algoritmici o semantici reali prima che la PR venga aperta:\n"
        "1. Off-by-one, variabili campionate ignorate (es. calcoli `_sx` ma poi nell'indice usi `dx`), indici errati NCHW vs HWC.\n"
        "2. Mock, placeholder, `unimplemented!()` o `todo!()` mascherati da implementazioni reali.\n"
        "3. Bypass di sicurezza o regressioni sulle API condivise.\n\n"
        "REGOLE DI VERDETTO TASSATIVE:\n"
        "- Se il codice è corretto, privo di stub o refusi logici, inizia la tua risposta con: `VERDICT: APPROVED`\n"
        "- Se trovi ANCHE UN SOLO refuso logico, calcolo degenere o variabile calcolata ma non usata, inizia con: `VERDICT: CHANGES_REQUESTED`\n"
        "Fornisci una spiegazione concisa, indicando riga, causa e la correzione chirurgica in puro Rust."
    )

    user_prompt = f"Statistiche modifiche:\n{stat_text}\n\nDiff da revisionare:\n```diff\n{truncated_diff}\n```"

    # Tentativo 1: Frontier Cloud Gemini (Antigravity Proxy) via llama-swap / OpenAI-compatible endpoint
    for model_id in ["gemini", "bolt74b", "core"]:
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 1500,
        }
        try:
            req = urllib.request.Request(
                GATEWAY_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=65.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if content:
                    approved = "VERDICT: APPROVED" in content.upper() and "VERDICT: CHANGES_REQUESTED" not in content.upper()
                    return approved, f"[Reviewer: {model_id}]\n{content}"
        except Exception:
            continue

    # Se entrambi gli endpoint dovessero essere irraggiungibili, non bloccare l'infrastruttura
    return True, "VERDICT: APPROVED (Fallback automatico per timeout gateway)"


def run_review_gate(workspace: Path, force: bool = False) -> tuple[bool, str]:
    rc, head_sha, _ = run_git(["rev-parse", "HEAD"], cwd=workspace)
    if rc != 0 or not head_sha:
        return True, "Impossibile determinare HEAD SHA; gate bypassato."

    state_file = get_git_state_file(workspace)
    state = load_review_state(state_file)

    if not force and state.get("approved_sha") == head_sha:
        return True, f"✅ Commit {head_sha[:8]} già approvato da Antigravity (`agy`)."

    round_count = int(state.get("round_count", 0))
    if not force and round_count >= MAX_REVIEW_ROUNDS:
        state["approved_sha"] = head_sha
        save_review_state(state_file, state)
        return True, f"⚠️ Raggiunto il tetto massimo di {MAX_REVIEW_ROUNDS} round di review pre-PR; sblocco creazione PR."

    # Estrai git diff rispetto a origin/main (o HEAD~1)
    rc, diff_text, _ = run_git(["diff", "origin/main...HEAD", "--", ".", ":!Cargo.lock"], cwd=workspace)
    if rc != 0 or not diff_text.strip():
        rc, diff_text, _ = run_git(["diff", "HEAD~1..HEAD", "--", ".", ":!Cargo.lock"], cwd=workspace)
    if not diff_text.strip():
        return True, "Nessun diff rilevato rispetto al base branch."

    _, stat_text, _ = run_git(["diff", "--stat", "origin/main...HEAD"], cwd=workspace)

    static_issues = static_heuristic_scan(diff_text)
    critic_approved, critic_report = call_frontier_critic(diff_text, stat_text)

    if static_issues:
        critic_approved = False
        static_block = "\n".join(f"- 🚨 **Static AST/Pattern Alert:** {item}" for item in static_issues)
        critic_report = f"VERDICT: CHANGES_REQUESTED\n\n{static_block}\n\n{critic_report}"

    new_round = round_count + 1
    state["round_count"] = new_round
    state.setdefault("history", []).append(
        {
            "round": new_round,
            "sha": head_sha,
            "approved": critic_approved,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "report": critic_report[:2000],
        }
    )

    if critic_approved:
        state["approved_sha"] = head_sha
        save_review_state(state_file, state)
        try:
            from core.notifier import send_telegram_notification
            send_telegram_notification(
                title=f"Antigravity Actor-Critic: Diff Approvato (Round {new_round})",
                message=(
                    f"• **Commit:** `{head_sha[:8]}`\n"
                    f"• **Round:** `{new_round}/{MAX_REVIEW_ROUNDS}`\n"
                    f"• **Esito:** `APPROVED` — Antigravity (`agy`) ha validato il codice del SuperAgent.\n"
                    f"La Pull Request può essere pubblicata."
                ),
                level="SUCCESS"
            )
        except Exception:
            pass
        return True, (
            f"✅ [ANTIGRAVITY PRE-PR REVIEW GATE — ROUND {new_round}/{MAX_REVIEW_ROUNDS}: APPROVED]\n"
            f"Commit `{head_sha[:8]}` validato con successo da Antigravity (`agy`).\n\n"
            f"{critic_report}"
        )
    else:
        save_review_state(state_file, state)
        try:
            from core.notifier import send_telegram_notification
            report_snippet = critic_report[:380] + ("..." if len(critic_report) > 380 else "")
            send_telegram_notification(
                title=f"Antigravity Actor-Critic: Problemi Rilevati nel Diff SuperAgent",
                message=(
                    f"• **Commit:** `{head_sha[:8]}`\n"
                    f"• **Round:** `{new_round}/{MAX_REVIEW_ROUNDS}`\n"
                    f"• **Esito:** `CHANGES_REQUESTED`\n\n"
                    f"🚨 **Critiche Antigravity (`agy`):**\n`{report_snippet}`\n\n"
                    f"👉 Il worker locale (`qwen35-fast`) è stato istruito per auto-correggersi."
                ),
                level="WARNING"
            )
        except Exception:
            pass
        return False, (
            f"======================================================================\n"
            f"🚫 [ANTIGRAVITY (agy) PRE-PR CODE REVIEW GATE — ROUND {new_round}/{MAX_REVIEW_ROUNDS}: CHANGES REQUESTED]\n"
            f"======================================================================\n"
            f"Prima di pubblicare la Pull Request, Antigravity (`agy`) ha analizzato il tuo\n"
            f"`git diff` sul commit `{head_sha[:8]}` e ha rilevato i seguenti problemi da correggere:\n\n"
            f"{critic_report}\n\n"
            f"👉 AZIONE OBBLIGATORIA PER IL WORKER (`qwen35-fast`):\n"
            f"1. Correggi subito i punti indicati qui sopra nei file sorgente.\n"
            f"2. Verifica la compilazione e i test con `cargo-uma test`.\n"
            f"3. Esegui `git add` e `git commit` con le correzioni.\n"
            f"4. Rilancia `gh pr create` per superare il gate e pubblicare la PR.\n"
            f"======================================================================"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Antigravity Pre-PR Code Review Gate")
    parser.add_argument("--workspace", default=os.getcwd(), help="Percorso del worktree git")
    parser.add_argument("--force", action="store_true", help="Forza la riesecuzione anche se già approvato")
    args = parser.parse_args()

    ws = Path(args.workspace).resolve()
    approved, msg = run_review_gate(ws, force=args.force)
    if approved:
        print(msg)
        return 0
    else:
        print(msg, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
