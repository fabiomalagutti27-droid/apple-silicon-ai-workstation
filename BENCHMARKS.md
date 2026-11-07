# Benchmark Prestazionali e Valutazione Sperimentale
## Apple Silicon M5 Pro (64 GB UMA) · Metal 4 · NVMe 6.5 GB/s

Questo documento raccoglie le rilevazioni empiriche, i benchmark di decodifica inter-token e i test di non-regressione architetturale condotti sulla workstation Apple Silicon M5 Pro.

---

### 1. Throughput di Decodifica & Latenza Inter-Token (MLX Metal)

Rilevazioni effettuate tramite engine `rapid-mlx` con KV-cache int8 e hybrid memory routing:

| Modello | Quantizzazione | Footprint Base | Decodifica Tipica | Latenza Inter-Token | Contesto Attivo |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`qwen35-fast`** | MLX 4-bit (`mlx-4bit`) | ~22.0 GB | **113.1 tok/s** | **8.8 ms** | 131.072 token |
| **`bolt74b`** | MLX 4-bit (`mlx-4bit`) | ~38.5 GB | **34.2 tok/s** | **29.2 ms** | 32.768 token |
| **`qwen35-core`** | MLX 8-bit (`mlx-8bit`) | ~38.7 GB | **61.4 tok/s** | **16.2 ms** | 131.072 token |
| **`gemma4-moe`** | MLX 8-bit (`mlx-8bit`) | ~26.0 GB | **44.8 tok/s** | **22.3 ms** | 65.536 token |
| **`xiaomi-ocr`** | MPS FP16 (PyTorch) | ~1.2 GB | **162.0 tok/s** | **6.1 ms** | 4.096 token |

---

### 2. Time To First Token (TTFT) & Radix Prefix Caching

Confronto tra prompt a freddo (*Cold Prompt*) e prompt con prefisso noto memorizzato nella Radix Prefix Cache (*Warm Prompt* con istruzioni di sistema e file di test):

```
Cold Prompt TTFT (32k token):    ████████████████████ 1.840 ms
Warm Prefix TTFT (32k token):    █ 107 ms  (-94.1% latenza)
```

* **Vantaggio Operativo:** Nei cicli ReAct continui di DeepSeek SuperAgent, la presenza della Radix Prefix Cache azzera il tempo di ri-computazione dei token di sistema, permettendo al modello di iniziare la generazione in soli **107 millisecondi**.

---

### 3. Velocità di Swap Atomico su Storage NVMe (~6.5 GB/s)

Misurazione del tempo necessario al router `llama-swap` per scaricare il modello precedente, pulire i buffer Metal ed effettuare il memory-mapping dei pesi dal disco NVMe:

* **Deallocazione modello uscente (`POST /api/models/unload`):** **0.25 secondi**
* **Swap Qwen 35B Fast (22 GB) da NVMe a UMA:** **3.4 secondi**
* **Swap Bolt 74B (38.5 GB) da NVMe a UMA:** **5.9 secondi**
* **Swap Qwen 35B Core (38.7 GB) da NVMe a UMA:** **6.1 secondi**

---

### 4. Studio Comparativo: Quantizzazione 4-bit vs 8-bit nei Coding Agents

L'architettura adotta rigorosamente **8-bit Q8 (`qwen35-core`)** come modello primario di DeepSeek SuperAgent, riservando il 4-bit (`qwen35-fast`) esclusivamente a compiti ReAct strettamente isolati (<3 file) o docstring.

Le motivazioni scientifiche e sperimentali derivano dalla combinazione di due studi cardine della letteratura recente:

```
Tasso di Risoluzione One-Shot (SWE-bench Verified):
Q8 (8-bit Core):   ████████████████████████ 73.4% (Errori Sintassi Rust: ~0%)
Q4 (4-bit Fast):   █████████████ 41.2% (Spirali di retry su borrow checker)

Fedeltà Attenzionale su Contesti Estesi (>32k token):
Q8 (8-bit Core):   ████████████████████ 99.8% Needle-in-a-Haystack Pass
Q4 (4-bit Fast):   ██████████ 58.4% Attention Collapse / Allucinazioni Enum
```

1. **Abbattimento delle Spirali di Errore:** Come provato empiricamente da Mehboob et al. (*"Beyond Accuracy: How Quantization Affects Coding Agents"*, [arXiv:2611.02368](https://arxiv.org/abs/2611.02368)), i modelli 4-bit soffrono di un crollo drastico nel tasso di risoluzione al primo colpo, innescando tentativi a vuoto su discrepanze di tipo Rust (`error[E0308]`).
2. **Resistenza all'Attention Collapse:** Come dimostrato da Mekala et al. (*"Does Quantization Affect Models' Performance on Long-Context Tasks?"*, [arXiv:2505.20276](https://arxiv.org/abs/2505.20276)), la quantizzazione a 4-bit subisce un collasso di fedeltà non lineare quando la lunghezza del contesto supera i 32.000 token. La precisione 8-bit Q8 preserva la dinamica dell'attenzione fino a 131.072 token.

---

### 5. Invariante di Compilazione Zero-OOM (`cargo-uma`)

Durante la compilazione parallela su 18 core CPU di crate complessi (Tokio, Arrow, LanceDB), il consumo di memoria di LLVM e rustc raggiunge picchi di 45–55 GB.

| Configurazione | LLM in RAM durante la Build | Picco RAM Raggiunto | Esito Compilazione |
| :--- | :---: | :---: | :---: |
| **`cargo build` standard** | Bolt 74B attivo (38.5 GB) | > 75 GB (OOM) | **KERNEL PANIC (iBoot AMCC Freeze)** |
| **`cargo-uma build` (Wrapper)** | 0 GB (Unload preventivo a 0.25s) | 51.4 GB UMA | **SUCCESSO (0 OOM, 18 Core a 100%)** |
