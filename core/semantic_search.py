#!/usr/bin/env python3
"""
semantic_search.py - Modulo di Indicizzazione ad Alto Contesto e Re-Ranking
Utilizza:
1. ModernBERT-base (139M) per embedding ad 8.192 token nativi (senza spezzature arbitrarie a 512 token).
2. BGE-Reranker-v2-m3 (568M) per cross-encoder re-ranking su Apple Silicon Metal (MPS) a bassa latenza.
Garantisce la massima precisione per la ricerca semantica nel Vault Obsidian e nei repository di codice.
"""

import sys
import os
import time
from typing import List, Dict, Any, Optional

_modernbert_model = None
_modernbert_tokenizer = None
_reranker_model = None
_reranker_tokenizer = None

def get_device() -> str:
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"


def get_modernbert():
    global _modernbert_model, _modernbert_tokenizer
    if _modernbert_model is None:
        import torch
        from transformers import AutoTokenizer, AutoModel
        device = get_device()
        model_id = "answerdotai/ModernBERT-base"
        _modernbert_tokenizer = AutoTokenizer.from_pretrained(model_id)
        _modernbert_model = AutoModel.from_pretrained(model_id).to(device).eval()
    return _modernbert_model, _modernbert_tokenizer


def get_reranker():
    global _reranker_model, _reranker_tokenizer
    if _reranker_model is None:
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        device = get_device()
        model_id = "BAAI/bge-reranker-v2-m3"
        _reranker_tokenizer = AutoTokenizer.from_pretrained(model_id)
        _reranker_model = AutoModelForSequenceClassification.from_pretrained(model_id).to(device).eval()
    return _reranker_model, _reranker_tokenizer


def compute_modernbert_embeddings(texts: List[str], max_length: int = 4096) -> List[List[float]]:
    """
    Calcola gli embedding vettoriali densi per una lista di testi o note Markdown (fino a 8k token).
    """
    import torch
    if not texts:
        return []

    model, tokenizer = get_modernbert()
    device = get_device()

    inputs = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=max_length,
        return_tensors="pt"
    ).to(device)

    with torch.no_grad():
        outputs = model(**inputs)
        # Mean pooling con attention mask
        token_embeddings = outputs.last_hidden_state
        input_mask_expanded = inputs["attention_mask"].unsqueeze(-1).expand(token_embeddings.size()).float()
        sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
        sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
        embeddings = (sum_embeddings / sum_mask)
        # Normalizzazione L2 per cosine similarity
        norm_embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

    return norm_embeddings.cpu().tolist()


def rerank_documents(query: str, documents: List[str], top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Valuta con Cross-Encoder la pertinenza di ciascun documento rispetto alla query e restituisce i top_k.
    """
    import torch
    if not documents or not query:
        return []

    model, tokenizer = get_reranker()
    device = get_device()

    pairs = [[query, doc] for doc in documents]
    inputs = tokenizer(
        pairs,
        padding=True,
        truncation=True,
        max_length=4096,
        return_tensors="pt"
    ).to(device)

    with torch.no_grad():
        outputs = model(**inputs)
        scores = outputs.logits.view(-1).float().cpu().tolist()

    ranked = sorted(
        [{"index": i, "document": doc, "score": score} for i, (doc, score) in enumerate(zip(documents, scores))],
        key=lambda x: x["score"],
        reverse=True
    )

    return ranked[:top_k]


if __name__ == "__main__":
    q = "Qual è la strategia di memoria per Bolt 74B su Apple Silicon?"
    docs = [
        "La ricetta della torta di mele richiede farina e uova fresche.",
        "NVIDIA Nemotron 3.5 Bolt 74B richiede quantizzazione del KV-cache a 8-bit per non superare i 52 GB UMA a 32k token di contesto.",
        "Il compilatore Rust rustc satura la CPU con 18 thread paralleli se non opportunamente limitato da cargo-uma.",
        "Il modello Xiaomi-OCR-0 converte PDF in KaTeX in 0.5 secondi."
    ]
    t0 = time.time()
    results = rerank_documents(q, docs, top_k=2)
    print(f"Reranking completato in {time.time() - t0:.3f}s:")
    for r in results:
        print(f" - [Score: {r['score']:.4f}] Doc {r['index']}: {r['document'][:80]}...")
