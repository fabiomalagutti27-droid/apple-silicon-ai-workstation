#!/usr/bin/env python3
"""
local_code_worker MCP Server
Espone il worker LLM locale MoE-First ad alto throughput su Mac mini M5 Pro per Antigravity,
Goose, OpenCode e Obsidian Copilot.
Include:
1. call_local_worker: inferenza MoE-First su Metal GPU (qwen35-fast, bolt74b, gemma4-moe, qwen35-core, gemini).
2. extract_document_ocr: pipeline specialistica Xiaomi-OCR-0 per estrarre Markdown & formule KaTeX da immagini e PDF.
3. delegate_to_antigravity: ponte di escalation per delegare task complessi ad Antigravity (agy).
"""

import os
import sys
import time
import json
import base64
import mimetypes
import subprocess
import urllib.request
import urllib.error
from typing import Optional, Dict, Any
from fastmcp import FastMCP

mcp = FastMCP("local-code-worker")

def get_default_mac_mini_host() -> str:
    import platform
    h = platform.node().lower()
    if "mini" in h or os.path.exists("/Users/fabiomalagutti/.config/llama-swap"):
        return "127.0.0.1"
    return os.environ.get("MAC_MINI_HOST", "127.0.0.1")

MAC_MINI_HOST = os.environ.get("MAC_MINI_HOST", get_default_mac_mini_host())
DEFAULT_PORT = int(os.environ.get("MAC_MINI_PORT", "8000"))
DEFAULT_MODEL = "qwen35-fast"


def _query_endpoint(port: int, payload: Dict[str, Any], timeout: float = 60.0) -> Dict[str, Any]:
    url = f"http://{MAC_MINI_HOST}:{port}/v1/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "Antigravity-Local-Worker"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


@mcp.tool()
def get_worker_status() -> str:
    """Verifica lo stato e la latenza dei motori LLM locali MoE-First sul Mac mini M5 Pro gestiti da llama-swap sulla porta 8000."""
    url = f"http://{MAC_MINI_HOST}:{DEFAULT_PORT}/v1/models"
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MCP-HealthCheck"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models_info = data.get("data", [])
            loaded = [m.get("id") for m in models_info if m.get("status", {}).get("value") == "loaded"]
            latency_ms = int((time.time() - t0) * 1000)
            return json.dumps({
                "gateway": f"http://{MAC_MINI_HOST}:{DEFAULT_PORT}/v1",
                "orchestrator": "llama-swap (MoE-First Unified Memory Router)",
                "status": "ONLINE",
                "latency_ms": latency_ms,
                "currently_in_ram": loaded if loaded else ["Standby (0 GB)"],
                "available_models_for_swap": [
                    "qwen35-fast (Qwen3.6 35B-A3B Q4 ~99 tok/s - SWE-bench 73.4% · Coding & Fast ReAct)",
                    "bolt74b (Nemotron 3.5 Bolt 74B A9B ~35 tok/s - Intelligence Index 21.4 · Triage & Reasoning)",
                    "qwen35-core (Qwen3.6 35B-A3B Q8 ~60 tok/s - FP16 Precision & Rust Architecture)",
                    "gemma4-moe (Gemma 4 26B-A4B Q8 ~43 tok/s - 256k Context & Vault Docente)",
                    "xiaomi-ocr (Xiaomi-OCR-0 0.8B VLM ~150+ tok/s - 1.2 GB VRAM · KaTeX & Markdown)",
                    "gemini (Gemini 3.8 Flash High - Frontier Cloud 0€ Proxy)"
                ]
            }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "gateway": f"http://{MAC_MINI_HOST}:{DEFAULT_PORT}/v1",
            "status": "OFFLINE",
            "error": str(e)
        }, indent=2, ensure_ascii=False)


@mcp.tool()
def call_local_worker(
    instruction: str,
    code_context: Optional[str] = "",
    model: Optional[str] = DEFAULT_MODEL,
    max_tokens: Optional[int] = 4096,
    temperature: Optional[float] = 0.2,
    port: Optional[int] = DEFAULT_PORT
) -> str:
    """
    Delega un compito di generazione codice, refactoring, scrittura test o docstring al worker locale sul Mac mini M5 Pro.
    Esegue su Metal GPU a costo zero token cloud, restituendo il codice generato e le metriche di velocità.
    Supporta lo swap automatico passando model='fast' (o 'qwen35-fast'), model='bolt' (o 'bolt74b'),
    model='core' (o 'qwen35-core'), model='gemma' (o 'gemma4-moe') o model='ocr'.
    """
    system_prompt = (
        "Sei un assistente di programmazione autonomo ad altissime prestazioni. "
        "Rispondi direttamente con il codice richiesto, preciso, tipizzato e pronto all'uso, "
        "seguito solo da spiegazioni essenziali e concise."
    )

    user_content = instruction
    if code_context and code_context.strip():
        user_content += f"\n\n```\n{code_context.strip()}\n```"

    target_model = (model or DEFAULT_MODEL).lower()
    if target_model in ["fast", "qwen35-fast", "kat", "kat-coder", "coder", "qwen"]:
        clean_model = "qwen35-fast"
    elif target_model in ["bolt", "bolt74b", "nemotron", "nemotron-bolt"]:
        clean_model = "bolt74b"
    elif target_model in ["core", "qwen35-core", "qwen-core"]:
        clean_model = "qwen35-core"
    elif target_model in ["gemma", "gemma4", "gemma4-moe"]:
        clean_model = "gemma4-moe"
    elif target_model in ["ocr", "xiaomi-ocr", "xiaomi-ocr-0"]:
        clean_model = "xiaomi-ocr"
    elif target_model in ["gemini", "gemini-flash"]:
        clean_model = "gemini"
    else:
        clean_model = target_model

    payload = {
        "model": clean_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    target_port = port or DEFAULT_PORT
    t0 = time.time()
    try:
        res = _query_endpoint(target_port, payload)
    except Exception as e:
        return f"ERRORE di connessione al worker locale (Porta {target_port}: {e})"

    elapsed = time.time() - t0
    choice = res.get("choices", [{}])[0].get("message", {})
    output_text = choice.get("content", "")
    if not output_text and choice.get("reasoning_content"):
        output_text = choice.get("reasoning_content")
    usage = res.get("usage", {})
    comp_tokens = usage.get("completion_tokens", 0)
    tok_sec = (comp_tokens / elapsed) if elapsed > 0 and comp_tokens > 0 else 0.0

    header = f"/* [WORKER LOCALE MAC MINI ({clean_model}) - Porta {target_port} - {comp_tokens} token in {elapsed:.2f}s ({tok_sec:.1f} tok/s)] */\n\n"
    return header + output_text


@mcp.tool()
def extract_document_ocr(
    file_path: str,
    instruction: Optional[str] = "Estrai fedelmente tutto il testo e converti le formule in KaTeX."
) -> str:
    """
    Stadio 1 della Document Pipeline: estrae testo Markdown e formule KaTeX perfette da immagini (PNG/JPG/WEBP) o documenti PDF
    utilizzando il Micro-VLM locale Xiaomi-OCR-0 (0.8B parametrizzato su Metal MPS a 150+ tok/s).
    Il testo formattato può poi essere inoltrato al modello Docente (gemma4-moe o bolt74b) per analisi concettuale.
    """
    resolved_path = os.path.expanduser(file_path)
    if not os.path.exists(resolved_path):
        return f"ERRORE: File '{resolved_path}' non trovato."

    mime, _ = mimetypes.guess_type(resolved_path)
    if not mime:
        mime = "application/octet-stream"

    # Se è un PDF, gestisci prima pagina o converti temporaneamente in immagine con sips o fitz se disponibile
    temp_img_path = None
    if mime == "application/pdf" or resolved_path.lower().endswith(".pdf"):
        temp_img_path = f"/tmp/ocr_page_{int(time.time())}.png"
        res = subprocess.run(["sips", "-s", "format", "png", resolved_path, "--out", temp_img_path], capture_output=True)
        if res.returncode == 0 and os.path.exists(temp_img_path):
            target_file = temp_img_path
            mime = "image/png"
        else:
            target_file = resolved_path
    else:
        target_file = resolved_path

    try:
        with open(target_file, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
    finally:
        if temp_img_path and os.path.exists(temp_img_path):
            try:
                os.remove(temp_img_path)
            except Exception:
                pass

    data_uri = f"data:{mime};base64,{b64_data}"
    payload = {
        "model": "xiaomi-ocr",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction or "Estrai fedelmente tutto il testo e converti le formule in KaTeX."},
                    {"type": "image_url", "image_url": {"url": data_uri}}
                ]
            }
        ],
        "max_tokens": 4096,
        "temperature": 0.1
    }

    t0 = time.time()
    try:
        res = _query_endpoint(DEFAULT_PORT, payload, timeout=90.0)
    except Exception as e:
        return f"ERRORE durante l'elaborazione OCR con Xiaomi-OCR-0: {e}"

    elapsed = time.time() - t0
    choice = res.get("choices", [{}])[0].get("message", {})
    output_text = choice.get("content", "")
    usage = res.get("usage", {})
    comp_tokens = usage.get("completion_tokens", 0)
    tok_sec = (comp_tokens / elapsed) if elapsed > 0 and comp_tokens > 0 else 0.0

    header = f"<!-- [XIAOMI-OCR-0: {comp_tokens} token estratti in {elapsed:.2f}s ({tok_sec:.1f} tok/s) da {os.path.basename(resolved_path)}] -->\n\n"
    return header + output_text


@mcp.tool()
def delegate_to_antigravity(
    task_description: str,
    context: Optional[str] = "",
    model_override: Optional[str] = "Gemini 3.8 Flash (High)"
) -> str:
    """
    Ponte di Escalation Ibrida per Goose, Obsidian ed OpenCode:
    Permette al modello locale di delegare un'analisi complessa, una sintesi ad ampio contesto o una refattorizzazione profonda
    direttamente al motore cloud frontier Antigravity (agy).
    """
    prompt = f"TASK DELEGATO DA RUNTIME LOCALE:\n{task_description}"
    if context and context.strip():
        prompt += f"\n\nCONTESTO RILEVANTE:\n{context.strip()}"

    agy_binary = "/Users/fabiomalagutti/.local/bin/agy"
    if not os.path.exists(agy_binary):
        import shutil
        agy_binary = shutil.which("agy") or "/opt/homebrew/bin/agy" or "agy"

    clean_model = "gemini-3.8-flash-high"
    if model_override:
        m_low = model_override.lower()
        if "flash" in m_low or "gemini" in m_low:
            clean_model = "gemini-3.8-flash-high"
        elif "opus" in m_low:
            clean_model = "claude-opus-5-5-high"
        elif "sonnet" in m_low:
            clean_model = "claude-sonnet-5-5-high"
        else:
            clean_model = model_override

    cmd = [
        agy_binary,
        "-p", prompt,
        "--model", clean_model,
        "--dangerously-skip-permissions"
    ]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        elapsed = time.time() - t0
        if proc.returncode == 0:
            header = f"/* [ANTIGRAVITY ESCALATION SUCCESS ({model_override}) in {elapsed:.2f}s] */\n\n"
            return header + proc.stdout.strip()
        else:
            return f"ERRORE durante la delega ad Antigravity (code {proc.returncode}): {proc.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return f"TIMEOUT: Antigravity ha impiegato più di 120s per completare la richiesta."
    except Exception as e:
        return f"ECCEZIONE durante la delega ad Antigravity: {e}"


@mcp.tool()
def prune_compiler_logs(raw_log: str, max_lines: Optional[int] = 100) -> str:
    """
    Densitomicro-filtro deterministico: estrae chirurgicamente in <2ms errori, panic e traceback
    da output prolissi di build (Rust/Cargo, Python, TypeScript), eliminando centinaia di righe
    di warning innocui e riducendo fino al 90% i token di contesto per l'agente.
    """
    sys.path.insert(0, "/Users/fabiomalagutti/ai-ecosystem")
    from core.log_pruner import prune_compiler_log
    return prune_compiler_log(raw_log, max_lines=max_lines or 100)


@mcp.tool()
def compress_agent_context(text: str, target_ratio: Optional[float] = 0.5) -> str:
    """
    Micro-compressore neurale basato su LLMLingua-2 (XLM-RoBERTa):
    Comprime del 50-70% ricerche web prolisse (ddg_search), dump JSON o lunghe cronologie di ticket,
    mantenendo inalterata la semantica e le entità chiave a zero impatto sulla VRAM dei modelli MoE.
    """
    sys.path.insert(0, "/Users/fabiomalagutti/ai-ecosystem")
    from core.context_compressor import compress_text_context
    return compress_text_context(text, target_ratio=target_ratio or 0.5)


@mcp.tool()
def rerank_vault_documents(query: str, candidate_chunks: list[str], top_k: Optional[int] = 3) -> str:
    """
    Cross-Encoder Re-Ranking su Apple Silicon Metal (MPS):
    Riordina semanticamente i frammenti di note Obsidian o codice recuperati per la query specificata,
    restituendo solo i top_k chunk a massima confidenza per eliminare le allucinazioni nel modello Docente.
    """
    sys.path.insert(0, "/Users/fabiomalagutti/ai-ecosystem")
    from core.semantic_search import rerank_documents
    results = rerank_documents(query, candidate_chunks, top_k=top_k or 3)
    return json.dumps(results, indent=2, ensure_ascii=False)




@mcp.tool()
def review_diff_with_antigravity(workspace_path: Optional[str] = None, force: Optional[bool] = False) -> str:
    """
    Pre-PR Code Review Gate (Actor-Critic Pattern):
    Sottopone il `git diff` del worktree corrente ad Antigravity (agy / Gemini Frontier Reviewer)
    per intercettare refusi algoritmici (es. `_sx` vs `dx`), calcoli dimensionali degeneri o stub
    incompleti PRIMA di eseguire `gh pr create`. Restituisce VERDICT: APPROVED o VERDICT: CHANGES_REQUESTED.
    """
    from pathlib import Path
    sys.path.insert(0, "/Users/fabiomalagutti/ai-ecosystem")
    from integrations.agy_pr_review_gate import run_review_gate
    ws = Path(workspace_path or os.getcwd()).resolve()
    approved, report = run_review_gate(ws, force=bool(force))
    return report


if __name__ == "__main__":
    mcp.run()
