"""Ollama auto-setup — install, configure, and optimize for voice assistant use.

Handles:
- Detecting if Ollama is installed
- Installing Ollama if missing
- Pulling recommended models
- Applying optimal settings for low TTFT (time-to-first-token)
- Advising on BYOM (bring-your-own-model) configuration
"""

from __future__ import annotations

import subprocess
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Recommended models for Clanker
_RECOMMENDED_MODELS = {
    "conversation": {
        "model": "llama3.2",
        "description": "General conversation and reasoning (3B, fast)",
        "size": "~2GB",
    },
    "conversation_large": {
        "model": "llama3.1:8b-instruct-q4_K_M",
        "description": "Better reasoning (8B, Q4_K_M quantization)",
        "size": "~4.5GB",
    },
    "vision": {
        "model": "llava",
        "description": "Vision/multimodal for camera descriptions",
        "size": "~4.5GB",
    },
    "embeddings": {
        "model": "nomic-embed-text",
        "description": "Embeddings for semantic memory search",
        "size": "~275MB",
    },
}

# Optimal Ollama options for voice assistant use (low TTFT)
VOICE_OPTIMIZED_OPTIONS: dict[str, Any] = {
    "num_ctx": 1024,        # small context = faster prompt eval
    "num_gpu": 999,         # offload all layers to GPU if available
    "num_batch": 512,       # default batch size
    "num_predict": 150,     # cap generation — voice responses are short
    "temperature": 0.3,     # lower temp = more deterministic for commands
    "keep_alive": -1,       # never unload — eliminates cold-start latency
}

# Environment variables for optimal Ollama server config
VOICE_OPTIMIZED_ENV = {
    "OLLAMA_FLASH_ATTENTION": "1",       # 10-30% TTFT reduction
    "OLLAMA_KV_CACHE_TYPE": "q8_0",      # quantized KV cache, saves VRAM
    "OLLAMA_NUM_PARALLEL": "1",          # single request = lowest latency
    "OLLAMA_MAX_LOADED_MODELS": "1",     # keep one model hot
}


def is_ollama_installed() -> bool:
    """Check if Ollama CLI is available."""
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def is_ollama_running(base_url: str = "http://localhost:11434") -> bool:
    """Check if Ollama server is reachable."""
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{base_url.rstrip('/')}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


def get_installed_models(
    base_url: str = "http://localhost:11434",
) -> list[dict[str, Any]]:
    """List models installed in Ollama."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{base_url.rstrip('/')}/api/tags")
            resp.raise_for_status()
            return resp.json().get("models", [])  # type: ignore[no-any-return]
    except Exception:
        return []


def install_ollama() -> dict[str, Any]:
    """Install Ollama via the official install script."""
    try:
        result = subprocess.run(
            ["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            return {"ok": True, "message": "Ollama installed successfully"}
        return {"ok": False, "message": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "Installation timed out"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def pull_model(
    model: str, base_url: str = "http://localhost:11434"
) -> dict[str, Any]:
    """Pull a model via Ollama CLI (shows progress)."""
    try:
        result = subprocess.run(
            ["ollama", "pull", model],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0:
            return {"ok": True, "message": f"Pulled {model}"}
        return {"ok": False, "message": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": f"Pull of {model} timed out"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def apply_systemd_env(env_vars: dict[str, str]) -> dict[str, Any]:
    """Apply environment variables to Ollama's systemd service.

    Creates an override file so settings persist across restarts.
    """
    override_dir = "/etc/systemd/system/ollama.service.d"
    override_file = f"{override_dir}/clanker-optimization.conf"

    env_lines = "\n".join(f"Environment={k}={v}" for k, v in env_vars.items())
    content = f"[Service]\n{env_lines}\n"

    try:
        import os

        os.makedirs(override_dir, exist_ok=True)
        with open(override_file, "w") as f:
            f.write(content)

        subprocess.run(["systemctl", "daemon-reload"], check=True, timeout=10)
        subprocess.run(
            ["systemctl", "restart", "ollama"], check=True, timeout=30
        )
        return {"ok": True, "message": f"Applied optimizations to {override_file}"}
    except PermissionError:
        return {
            "ok": False,
            "message": "Need root to configure systemd. Run with sudo.",
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def get_optimization_advice(
    *,
    has_gpu: bool = False,
    ram_gb: int = 16,
    use_case: str = "voice_assistant",
) -> dict[str, Any]:
    """Generate optimization recommendations based on hardware.

    Returns recommended Ollama options, environment variables, and
    model suggestions.
    """
    advice: dict[str, Any] = {
        "model": "llama3.2",
        "options": dict(VOICE_OPTIMIZED_OPTIONS),
        "env": dict(VOICE_OPTIMIZED_ENV),
        "tips": [],
    }

    if has_gpu:
        advice["tips"].append(
            "GPU detected — all layers will be offloaded (num_gpu: 999). "
            "This gives 5-10x faster inference vs CPU."
        )
        if ram_gb >= 24:
            advice["model"] = "llama3.1:8b-instruct-q4_K_M"
            advice["tips"].append(
                "24GB+ VRAM: using 8B Q4_K_M for better quality. "
                "You could also try 13B models."
            )
    else:
        advice["options"]["num_gpu"] = 0
        advice["tips"].append(
            "No GPU — using CPU inference. Consider a used RTX 3060 "
            "(~$200) for 5-10x speed improvement."
        )
        if ram_gb <= 8:
            advice["model"] = "llama3.2:1b"
            advice["options"]["num_ctx"] = 512
            advice["tips"].append(
                "Low RAM: using 1B model with reduced context. "
                "Responses will be faster but less capable."
            )

    advice["tips"].append(
        "keep_alive: -1 keeps the model loaded permanently. "
        "Eliminates 2-5s cold-start delay on first request."
    )
    advice["tips"].append(
        "OLLAMA_FLASH_ATTENTION=1 reduces TTFT by 10-30%. Always enable."
    )
    advice["tips"].append(
        "num_predict: 150 caps response length — voice responses should "
        "be brief. Prevents runaway generation."
    )

    return advice
