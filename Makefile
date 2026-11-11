# ==============================================================================
# Makefile - Apple Silicon AI Workstation
# Single-command developer ergonomics for setup, serving, testing, and backup
# ==============================================================================

SHELL := /usr/bin/env bash
PYTHON ?= python3

.PHONY: help setup kernel models services status test lint backup clean

help:
	@echo "Apple Silicon AI Workstation CLI"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Lifecycle Targets:"
	@echo "  setup       Run automated bootstrap.sh (Homebrew, uv, directories, cargo-uma)"
	@echo "  kernel      Elevate Metal UMA wired memory limit to 56 GB (requires sudo)"
	@echo "  models      Download open-weight MoE and Micro-VLM checkpoints from Hugging Face"
	@echo "  services    Install and launch macOS LaunchAgents via install_services.sh"
	@echo ""
	@echo "Operational Targets:"
	@echo "  status      Inspect health of llama-swap (:8000), SuperAgent (:3082), OpenCode (:49374)"
	@echo "  test        Execute unit tests across core sanitization, pruning, and MCP tools"
	@echo "  lint        Run linter and syntax checks across Python and Shell scripts"
	@echo "  backup      Trigger immediate compressed backup and sync to Google Drive via rclone"
	@echo "  clean       Remove temporary test caches, logs, and build artifacts"
	@echo ""

setup:
	@chmod +x bootstrap.sh scripts/*.sh
	@./bootstrap.sh

kernel:
	@chmod +x scripts/setup_wired_limit.sh
	@sudo bash scripts/setup_wired_limit.sh

models:
	@chmod +x scripts/download_models.sh
	@bash scripts/download_models.sh

services:
	@chmod +x scripts/install_services.sh
	@bash scripts/install_services.sh

status:
	@echo "=== Apple Silicon Compute Node Health Status ==="
	@echo -n "• Wired Metal Limit:  "
	@sysctl -n iogpu.wired_limit_mb 2>/dev/null && echo " MB" || echo "Not configured"
	@echo -n "• llama-swap (:8000): "
	@curl -s -m 2 http://127.0.0.1:8000/health >/dev/null 2>&1 && echo "[ONLINE]" || echo "[OFFLINE]"
	@echo -n "• SuperAgent (:3082): "
	@(curl -s -m 2 http://127.0.0.1:3082/api/m5-stats >/dev/null 2>&1 || curl -s -m 2 http://$${MAC_MINI_HOST:-127.0.0.1}:3082/api/m5-stats >/dev/null 2>&1) && echo "[ONLINE]" || echo "[OFFLINE]"
	@echo -n "• OpenCode   (:49374): "
	@curl -s -m 2 http://127.0.0.1:49374/ >/dev/null 2>&1 && echo "[ONLINE]" || echo "[OFFLINE]"

test:
	@echo "--> Running test suite..."
	@$(PYTHON) -m unittest discover -s tests -p "test_*.py"

lint:
	@echo "--> Checking Python syntax and style..."
	@$(PYTHON) -m py_compile core/*.py mcp/local_code_worker/*.py bin/*.py integrations/*.py
	@echo "[OK] Python files compiled without syntax errors."
	@if command -v shellcheck >/dev/null 2>&1; then \
		echo "--> Checking Shell scripts with shellcheck..."; \
		shellcheck bootstrap.sh scripts/*.sh; \
		echo "[OK] Shell scripts passed validation."; \
	fi

backup:
	@chmod +x scripts/backup_to_gdrive.sh
	@bash scripts/backup_to_gdrive.sh

clean:
	@echo "--> Cleaning temporary files..."
	@rm -rf .pytest_cache tests/__pycache__ core/__pycache__ mcp/local_code_worker/__pycache__
	@find . -name "*.pyc" -delete
	@echo "[OK] Clean completed."
