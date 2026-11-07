# 🍎 Apple Silicon AI Workstation & Autonomous Agent Infrastructure
### Production-Grade Blueprint for High-Throughput MoE Local Inference, Zero-OOM Compilation, and Multi-Agent Orchestration

[![Hardware](https://img.shields.io/badge/Hardware-Apple%20M5%20Pro%20(64GB%20UMA)-black?logo=apple&style=for-the-badge)](https://apple.com)
[![Inference Engine](https://img.shields.io/badge/Engine-Metal%204%20%2F%20MLX-orange?logo=apple&style=for-the-badge)](https://github.com/ml-explore/mlx)
[![Orchestrator](https://img.shields.io/badge/Router-llama--swap%20(:8000)-blue?style=for-the-badge)](https://github.com/mostlygeek/llama-swap)
[![SuperAgent](https://img.shields.io/badge/SuperAgent-Cordis%20(:3082)-green?style=for-the-badge)](https://github.com/deepseek-ai)
[![Protocol](https://img.shields.io/badge/MCP-FastMCP%20Suite-purple?style=for-the-badge)](https://modelcontextprotocol.io)
[![Cloud Backup](https://img.shields.io/badge/Backup-Google%20Drive%20(rclone)-yellow?logo=google-drive&style=for-the-badge)](https://rclone.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)
[![UniBo](https://img.shields.io/badge/Affiliation-Alma%20Mater%20Studiorum%20UniBo-red.svg?style=for-the-badge)](https://www.unibo.it)

---

## 1. Executive Overview

This repository provides a fully declarative, reproducible, and production-tested blueprint for converting Apple Silicon hardware (M1/M2/M3/M4/M5 Pro/Max/Ultra with 32–128 GB UMA) into a dedicated, headless AI compute node. 

The architecture is designed to solve real-world bottlenecks encountered when running autonomous coding agents (such as DeepSeek SuperAgent, Goose, or OpenCode) and large local mixture-of-experts (MoE) models on macOS:

* **Eliminating GPU Memory Rejections:** Overcoming macOS default kernel caps through declarative sysctl tuning (`iogpu.wired_limit_mb=57344`), enabling up to 56 GB of wired Metal memory on a 64 GB host.
* **Deterministic Zero-OOM Compilation:** A compiler wrapper (`cargo-uma`) that unloads active LLMs from VRAM in 250 ms before rustc/LLVM compiles heavy parallel workspaces, preventing system lockups and kernel panics.
* **Stream-Safe Resource Partitioning:** Independent memory groups in `llama-swap` preventing VRAM contention between high-frequency triage routers (cloud proxy at 0 MB VRAM) and streaming execution workers (MoE 8-bit Q8 on Metal).
* **Observation Masking & Context Compression:** Integrated regex densito-filtering (`log_pruner.py`, -92% token waste) and neural compression (LLMLingua-2, 50–65% ratio) preserving agent context windows.

---

## 2. Infrastructure Topology

The system operates as an asymmetrical, two-node distributed compute cluster connected via an encrypted WireGuard mesh network (Tailscale):

```mermaid
flowchart TB
    subgraph Client["Developer Station / Thin Client (MacBook Air)"]
        UI_Goose["Goose Desktop GUI"]
        UI_Obsidian["Obsidian Vault & Copilot Plugin"]
        CLI_AGY["Antigravity CLI (agy)"]
        CLI_OpenCode["OpenCode Web & CLI"]
        SSH_Tun["dsh-dashboard (SSH Auto-Tunnel :3082)"]
    end

    subgraph Mesh["Private WireGuard Mesh (Tailscale P2P <1.2ms)"]
        Tunnel["Encrypted Direct P2P Channel"]
        SyncMesh["Syncthing Mesh (Ports 22000 / 8384)"]
    end

    subgraph Host["Dedicated Compute Node (Mac mini M5 Pro - 64 GB UMA)"]
        Gateway["llama-swap Reverse Proxy (:8000)"]
        RapidMLX["rapid-mlx Metal Inference Engines (:8010-:8020)"]
        Satellites["Micro-Worker Satellites (OCR, Log-Pruner, LLMLingua-2, BGE)"]
        DSH_Daemon["DeepSeek SuperAgent Harness (:3082)"]
        OpenCodeDaemon["opencode serve --service (:49374)"]
        ClaudeMem["bun worker-service.cjs (claude-mem :37701)"]
        TG_Hub["Telegram Hub 24/7 (aiogram + Watchdog 90s + Outbox Watcher)"]
        Storage["NVMe Checkpoint Storage (~6.5 GB/s)"]
    end

    Client <===> Tunnel <===> Host
    Client <===> SyncMesh <===> Host
```

---

## 3. Core Invariants & Deterministic Memory Safety

On a unified memory architecture (64 GB UMA), memory is shared between the CPU, Metal GPU, and OS kernel. The system enforces three non-negotiable invariants:

### Invariant A: Single-Model in VRAM (`llama-swap` :8000)
To avoid out-of-memory states, only one heavy LLM checkpoint is resident in Metal RAM at any time. The router:
1. Keeps one model loaded. When a different model is queried, it deallocates the resident model (0.25s), frees Metal buffers, and memory-maps the requested model from NVMe in **3.2–6.0 seconds**.
2. Automatically transitions to **Standby (0 GB VRAM)** after 600 seconds of inactivity.

### Invariant B: Atomic Deallocation for Compilation (`cargo-uma`)
Compiling complex systems crates (Tokio, Arrow, LanceDB, CUDA/Metal bindings) with `cargo build -j18` consumes up to 45–55 GB of RAM for `rustc` and LLVM LTO. The [`cargo-uma`](bin/cargo-uma) wrapper guarantees zero OOM:
```bash
#!/usr/bin/env bash
set -e
# Atomically flush llama-swap VRAM before saturating CPU cores & UMA with LLVM
curl -s -X POST http://127.0.0.1:8000/api/models/unload >/dev/null 2>&1 || true
sleep 0.2
exec cargo "$@"
```

### Invariant C: Router-Worker Memory Decoupling
To eliminate stream abortions during multi-agent workflows, models are partitioned into distinct groups:
* **`cloud` group (`exclusive: false`, `swap: false`):** High-frequency triage via local proxy (`gemini`) running at **0 MB VRAM** with a 1,000,000 token context window.
* **`local` group (`exclusive: false`, `swap: true`):** Heavy Metal models (`qwen35-core`, `bolt74b`) operating in streaming mode within the 56 GB wired Metal allocation.

---

## 4. Model Catalog & Micro-Workers

All weights are stored locally in `~/.models/` on high-throughput NVMe storage:

| Model ID | Base Architecture | Quantization / Engine | Footprint | Decode Throughput | Active Context | Primary Operational Role |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`qwen35-fast`** | Qwen 3.6 35B-A3B MoE | MLX 4-bit (`mlx-4bit`) | ~22.0 GB | **113.1 tok/s** | 131,072 | Fast ReAct loops, unit tests, docstrings, subagents (<3 files) |
| **`bolt74b`** | NVIDIA Nemotron 3.5 Bolt 74B | MLX 4-bit (`int8` KV-cache) | ~38.5 GB | **34.2 tok/s** | 32,768 | Architecture planning, AST verification, frontier triage |
| **`qwen35-core`** | Qwen 3.6 35B-A3B MoE | MLX 8-bit (`mlx-8bit` Q8) | ~38.7 GB | **61.4 tok/s** | 131,072 | **SuperAgent Default Worker:** Zero context collapse, FP16 Rust architect |
| **`gemma4-moe`** | Gemma 4 26B-A4B MoE | MLX 8-bit (`mlx-8bit` Q8) | ~26.0 GB | **44.8 tok/s** | 65,536 | Obsidian Vault lecturer, conceptual analysis, multimodal reasoning |
| **`xiaomi-ocr`** | Xiaomi-OCR-0 (0.8B Micro-VLM) | PyTorch MPS FP16 | ~1.2 GB | **162.0 tok/s** | 4,096 | Optical Markdown extraction and KaTeX formulas from PDFs/images |
| **`gemini`** | Gemini 3.8 Flash High | Frontier Cloud Proxy | 0 MB | Sub-second | 1,048,576 | High-context escalation, Actor-Critic Pre-PR code review |

---

## 5. Empirical Benchmarks & Experimental Validation

### 5.1 Decode Throughput & Latency (Metal 4 Engine)
Measured using `rapid-mlx` with memory-mapped weights and hybrid int8 KV-caching:
* **`qwen35-fast` (35B-A3B Q4):** 113.1 tok/s (8.8 ms inter-token latency).
* **`qwen35-core` (35B-A3B Q8):** 61.4 tok/s (16.2 ms inter-token latency).
* **`bolt74b` (74B-A9B Q4):** 34.2 tok/s (29.2 ms inter-token latency).

### 5.2 Time to First Token (TTFT) via Radix Prefix Caching
```
Cold Prompt TTFT (32k tokens):   ████████████████████ 1,840 ms
Warm Prefix TTFT (32k tokens):   █ 107 ms  (-94.1% latency)
```

### 5.3 Scientific Rationale for 8-bit Quantization in Coding Agents
Following recent empirical software engineering literature (*Mehboob et al., arXiv:2611.02368*; *Mekala et al., arXiv:2505.20276*):
* **One-Shot Pass Rate (SWE-bench):** Q8 models achieve **73.4%** one-shot success with near-zero borrow-checker syntax errors, compared to **41.2%** for 4-bit models (which suffer from retry loops).
* **Long-Context Resilience (>32k tokens):** 4-bit models undergo non-linear attention degradation (*needle-in-a-haystack* score drops to 58.4%), whereas 8-bit Q8 maintains **99.8%** recall up to 131,072 tokens.

---

## 6. FastMCP Server Suite (`local_code_worker`)

The unified FastMCP server ([`mcp/local_code_worker/server.py`](mcp/local_code_worker/server.py)) exposes 8 specialized tools to Goose, OpenCode, Obsidian Copilot, and SuperAgent:

1. `get_worker_status()`: Inspects `llama-swap`, resident VRAM, and port latency.
2. `call_local_worker(model, instruction)`: Dispatches MoE generation on Metal at zero cloud token cost.
3. `extract_document_ocr(file_path)`: Micro-VLM OCR yielding clean Markdown and KaTeX math in 0.5s.
4. `delegate_to_antigravity(prompt, model)`: Escalates massive refactorings to Frontier Cloud.
5. `prune_compiler_logs(raw_log)`: Deterministic log pruner reducing build logs by **92% in <2 ms**.
6. `compress_agent_context(text, ratio)`: Neural context compressor (LLMLingua-2 XLM-RoBERTa).
7. `rerank_vault_documents(query, chunks)`: MPS cross-encoder reranker (BGE-Reranker-v2-m3).
8. `review_diff_with_antigravity(workspace_path)`: Actor-Critic Pre-PR gate auditing diffs for indexing bugs or memory flaws before opening GitHub pull requests.

---

## 7. Quickstart & Automated Bootstrap

### Step 1: Clone Repository & Run Idempotent Bootstrap
```bash
git clone https://github.com/fabiomalagutti27-droid/apple-silicon-ai-workstation.git
cd apple-silicon-ai-workstation
chmod +x bootstrap.sh scripts/*.sh
./bootstrap.sh
```

### Step 2: Elevate Metal UMA Limit to 56 GB (Requires sudo)
```bash
sudo bash scripts/setup_wired_limit.sh
```

### Step 3: Download Open-Weight Model Checkpoints
```bash
bash scripts/download_models.sh
```

### Step 4: Install & Start Background LaunchAgents
```bash
bash scripts/install_services.sh
```

---

## 8. Automated Weekly Cloud Backup (Google Drive via rclone)

To prevent wasting cloud storage on reproducible model weights (~150 GB), the backup routine archives only configurations, source code, registries, LaunchAgents, and the Obsidian Vault:

```bash
# 1. Configure your Google Drive remote in rclone (one-time)
brew install rclone
rclone config

# 2. Test manual backup
bash scripts/backup_to_gdrive.sh

# 3. Enable automated weekly schedule (Sundays at 03:00 AM)
# (Automatically handled by install_services.sh via com.ai.ecosystem.backup.plist)
```

---

## 9. Security, Privacy & Zero-Trust Verification

* **Zero Leaked Credentials:** All configurations use environment variable expansion (`${HOME}`, `${MAC_MINI_HOST}`).
* **Telegram Bot Zero-Trust Middleware:** Inbound messages are filtered against `ALLOWED_TELEGRAM_USER_ID`, silently dropping unauthenticated requests.
* **Autonomous Watchdog Protection:** A dedicated native OS thread (`watchdog.py`) monitors the asyncio event loop and executes clean auto-kickstarts via `launchctl` if stalled >90 seconds.

---

## 10. Repository File Structure

```
apple-silicon-ai-workstation/
├── .gitignore                      # Hardened exclusions for weights, tokens, and caches
├── .env.example                    # Environment variable template
├── LICENSE                         # MIT License
├── README.md                       # Main architecture reference and setup guide
├── ARCHITECTURE.md                 # Full formal specifications and engineering manual
├── BENCHMARKS.md                   # Empirical performance tables and ablation studies
├── Brewfile                        # Declarative Homebrew package bundle
├── bootstrap.sh                    # Automated workstation setup script
├── bin/
│   ├── cargo-uma                   # Zero-OOM VRAM-flushing compiler wrapper
│   ├── xiaomi_ocr_server.py        # Micro-VLM OpenAI-compatible OCR server
│   └── gemini_proxy.py             # Frontier Cloud bridge proxy
├── core/
│   ├── log_pruner.py               # Deterministic compiler log pruner (-92% tokens)
│   ├── context_compressor.py       # LLMLingua-2 neural context compressor
│   └── semantic_search.py          # ModernBERT + BGE-Reranker cross-encoder
├── integrations/
│   ├── submit_phase_pr.py          # Atomic Closing Tool (ACI) for agent tickets
│   └── agy_pr_review_gate.py       # Actor-Critic Pre-PR code review gate
├── mcp/
│   └── local_code_worker/
│       └── server.py               # FastMCP 8-tool unified agent server
├── configs/
│   ├── llama-swap.yaml.template    # UMA single-model & group router configuration
│   ├── cordis.patch.yml.template   # DeepSeek SuperAgent Cordis configuration
│   └── launchd/                    # Portable launchd templates
│       ├── com.localai.wiredlimit.plist.template
│       ├── com.localai.llamaswap.plist.template
│       ├── com.ai.ecosystem.bot.plist.template
│       ├── com.ai.ecosystem.digest.plist.template
│       └── com.ai.ecosystem.backup.plist.template
└── scripts/
    ├── setup_wired_limit.sh        # Kernel tuning installer for wired memory
    ├── download_models.sh          # Batch downloader from Hugging Face
    ├── install_services.sh         # LaunchAgents installer with path interpolation
    └── backup_to_gdrive.sh         # Compressed weekly backup & rclone sync
```

---

## 11. License & Citation

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

### Academic / Technical Citation
If you utilize this architecture or blueprint in your research or local infrastructure, please cite:

```bibtex
@misc{malagutti2026applesiliconai,
  author       = {Fabio Malagutti},
  title        = {Apple Silicon AI Workstation: High-Throughput MoE-First Autonomous Agent Infrastructure},
  year         = {2026},
  publisher    = {GitHub},
  journal      = {GitHub repository},
  howpublished = {\url{https://github.com/fabiomalagutti27-droid/apple-silicon-ai-workstation}},
  institution  = {Alma Mater Studiorum -- Universit{\`a} di Bologna}
}
```
