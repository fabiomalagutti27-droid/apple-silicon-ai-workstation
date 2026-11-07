#!/usr/bin/env python3
"""
context_compressor.py - Modulo Unificato di Compressione del Contesto
Combina:
1. Log-Pruner Deterministico (<2ms, 0 MB VRAM) per output di compilazione e test (Cargo, pytest, tsc).
2. LLMLingua-2 Neurale (XLM-RoBERTa, CPU/MPS) per compressione 2x-3x di ricerche web e documenti prolissi.
"""

import sys
import os
from typing import Optional
from core.log_pruner import prune_compiler_log

_llmlingua_compressor = None

def get_neural_compressor():
    global _llmlingua_compressor
    if _llmlingua_compressor is None:
        try:
            from llmlingua import PromptCompressor
            _llmlingua_compressor = PromptCompressor(
                model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
                use_llmlingua2=True,
                device_map="cpu"
            )
        except Exception as e:
            sys.stderr.write(f"Avviso: Impossibile inizializzare LLMLingua-2 ({e})\n")
            return None
    return _llmlingua_compressor


def compress_text_context(text: str, target_ratio: float = 0.5) -> str:
    """
    Comprime un blocco di testo o una ricerca web usando LLMLingua-2.
    Se il testo è inferiore a 200 caratteri, lo restituisce intatto.
    """
    if not text or len(text) < 200:
        return text

    compressor = get_neural_compressor()
    if not compressor:
        return text

    try:
        res = compressor.compress_prompt(
            text,
            rate=target_ratio,
            force_tokens=["\n", "?", "{", "}", "[", "]", ":"]
        )
        compressed = res.get("compressed_prompt", text)
        orig_tokens = res.get("origin_tokens", 0)
        comp_tokens = res.get("compressed_tokens", 0)
        saving = 100 - int((comp_tokens / orig_tokens) * 100) if orig_tokens > 0 else 0
        header = f"<!-- [LLMLINGUA-2: {orig_tokens} -> {comp_tokens} token (-{saving}%)] -->\n\n"
        return header + compressed
    except Exception as e:
        sys.stderr.write(f"Errore compressione LLMLingua-2: {e}\n")
        return text


def auto_compress(content: str, is_compiler_log: bool = False, target_ratio: float = 0.5) -> str:
    """
    Riconosce automaticamente il tipo di input:
    - Se è un log di errore/compilazione -> esegue il Log-Pruner deterministico.
    - Se è testo narrativo/ricerca web prolissa -> esegue LLMLingua-2.
    """
    if is_compiler_log or "error[" in content or "warning[" in content or "Traceback" in content:
        return prune_compiler_log(content)
    
    return compress_text_context(content, target_ratio=target_ratio)
