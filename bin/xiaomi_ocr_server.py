#!/usr/bin/env python3
"""
xiaomi_ocr_server.py - OpenAI-compatible micro-server for Xiaomi-OCR-0 (0.8B VLM) on Apple Silicon Metal (MPS).
Listens on --port (dynamic from llama-swap) and provides /v1/chat/completions & /health.
"""
import argparse
import base64
import io
import json
import os
import re
import sys
import time
from aiohttp import web
from pathlib import Path
from PIL import Image
import torch
from transformers import AutoModelForImageTextToText, AutoProcessor

parser = argparse.ArgumentParser(description="Xiaomi-OCR-0 OpenAI-compatible server")
parser.add_argument("--host", type=str, default="127.0.0.1")
parser.add_argument("--port", type=int, default=8015)
parser.add_argument("--model-path", type=str, default=str(Path.home() / ".models/xiaomi-ocr-0"))
args = parser.parse_args()

print(f"Loading Xiaomi-OCR-0 from {args.model_path} onto Apple Metal MPS...")
device = "mps" if torch.backends.mps.is_available() else "cpu"
dtype = torch.float16 if device == "mps" else torch.float32

model = AutoModelForImageTextToText.from_pretrained(args.model_path, dtype=dtype).to(device).eval()
processor = AutoProcessor.from_pretrained(args.model_path)
print(f"[OK] Xiaomi-OCR-0 ready on {device} (VRAM: ~1.2 GB)")

async def health_handler(request):
    return web.json_response({"status": "ok", "model": "xiaomi-ocr-0"})

def extract_image_from_content(content):
    if isinstance(content, str):
        return None
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "image_url":
                    url = part.get("image_url", {}).get("url", "")
                    if url.startswith("data:image"):
                        # Base64 data URI
                        header, b64_data = url.split(",", 1)
                        img_bytes = base64.b64decode(b64_data)
                        return Image.open(io.BytesIO(img_bytes)).convert("RGB")
                    elif os.path.exists(url):
                        return Image.open(url).convert("RGB")
                elif part.get("type") == "image" and "image" in part:
                    img = part["image"]
                    if isinstance(img, Image.Image):
                        return img.convert("RGB")
                    elif isinstance(img, str) and os.path.exists(img):
                        return Image.open(img).convert("RGB")
    return None

def extract_prompt_from_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                return part.get("text", "")
    return "Extract all information from the main body of the document image and represent it in markdown format with LaTeX formulas."

async def chat_completions(request):
    try:
        data = await request.json()
        messages = data.get("messages", [])
        
        target_image = None
        user_prompt = "Extract all information from the main body of the document image and represent it in markdown format with LaTeX formulas."
        
        for msg in reversed(messages):
            if msg.get("role") == "user":
                img = extract_image_from_content(msg.get("content"))
                if img is not None:
                    target_image = img
                prompt = extract_prompt_from_content(msg.get("content"))
                if prompt:
                    user_prompt = prompt
                if target_image:
                    break

        if target_image is None:
            # Fallback if no image provided
            res_text = "Nessuna immagine fornita per l'estrazione OCR."
        else:
            inputs = processor.apply_chat_template(
                [{
                    "role": "user",
                    "content": [
                        {"type": "image", "image": target_image},
                        {"type": "text", "text": user_prompt}
                    ]
                }],
                tokenize=True,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt"
            ).to(device)

            with torch.inference_mode():
                output = model.generate(**inputs, max_new_tokens=4096, do_sample=False)
            new_tokens = output[:, inputs["input_ids"].shape[1]:]
            res_text = processor.batch_decode(new_tokens, skip_special_tokens=True)[0]

        resp = {
            "id": f"chatcmpl-ocr-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "xiaomi-ocr",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": res_text
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": len(res_text.split()),
                "total_tokens": 100 + len(res_text.split())
            }
        }
        return web.json_response(resp)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

app = web.Application(client_max_size=50 * 1024 * 1024)
app.router.add_get("/health", health_handler)
app.router.add_post("/v1/chat/completions", chat_completions)

if __name__ == "__main__":
    web.run_app(app, host=args.host, port=args.port)
