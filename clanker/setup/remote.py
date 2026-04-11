"""Remote deployment of Clanker via SSH.

For users running HA Container or HA Core (not HA OS) who want to
deploy Clanker to the same server.  Uses subprocess + ssh/scp — no
paramiko dependency needed.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent


def _run_ssh(host: str, command: str, *, timeout: int = 30) -> dict[str, Any]:
    """Run a command on a remote host via SSH."""
    from clanker.setup.ssh_keys import get_ssh_key_args

    try:
        key_args = get_ssh_key_args()
        host_parts = host.strip().split()
        result = subprocess.run(
            [
                "ssh", "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10",
                *key_args, *host_parts, command,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "SSH connection timed out"}
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "stderr": "ssh command not found"}


def _run_scp(local_path: str, remote_dest: str, *, timeout: int = 60) -> dict[str, Any]:
    """Copy a file/directory to a remote host via SCP."""
    try:
        result = subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", "-r", local_path, remote_dest],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": result.returncode == 0,
            "stderr": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stderr": "SCP timed out"}
    except FileNotFoundError:
        return {"ok": False, "stderr": "scp command not found"}


def test_ssh(host: str) -> dict[str, Any]:
    """Test SSH connectivity to a remote host.

    Args:
        host: SSH destination (e.g. ``user@192.168.1.50``).

    Returns:
        Dict with ``ok``, ``message``, and detected capabilities.
    """
    result = _run_ssh(host, "echo ok")
    if not result["ok"]:
        return {"ok": False, "message": f"SSH failed: {result['stderr']}"}

    # Check capabilities
    caps: dict[str, bool] = {
        "docker": False,
        "docker_compose": False,
        "python3": False,
        "ha_config": False,
    }

    r = _run_ssh(host, "docker --version 2>/dev/null")
    caps["docker"] = r["ok"]

    r = _run_ssh(host, "docker compose version 2>/dev/null || docker-compose --version 2>/dev/null")
    caps["docker_compose"] = r["ok"]

    r = _run_ssh(host, "python3 --version 2>/dev/null")
    caps["python3"] = r["ok"]

    # Check for HA config directory
    for path in ["/config", "/root/homeassistant", "/home/*/homeassistant"]:
        r = _run_ssh(host, f"test -f {path}/configuration.yaml && echo found")
        if r["ok"] and "found" in r["stdout"]:
            caps["ha_config"] = True
            caps["ha_config_path"] = path  # type: ignore[assignment]
            break

    return {
        "ok": True,
        "message": "SSH connected",
        "capabilities": caps,
    }


def deploy_docker(
    host: str,
    *,
    ha_config_path: str = "/config",
    install_dir: str = "/opt/clanker",
) -> dict[str, Any]:
    """Deploy Clanker to a remote host via Docker.

    1. Creates the install directory
    2. Copies project files via SCP
    3. Installs the HA custom component
    4. Starts the container via docker-compose

    Args:
        host: SSH destination.
        ha_config_path: Path to HA's config directory on the remote host.
        install_dir: Where to install Clanker on the remote host.

    Returns:
        Dict with ``ok``, ``message``, and step details.
    """
    steps: list[dict[str, Any]] = []

    # 1. Create install directory
    r = _run_ssh(host, f"mkdir -p {install_dir}")
    steps.append({"step": "create_dir", **r})
    if not r["ok"]:
        return {"ok": False, "message": f"Failed to create {install_dir}", "steps": steps}

    # 2. Create a deploy tarball
    with tempfile.TemporaryDirectory() as tmpdir:
        tarball = Path(tmpdir) / "clanker-deploy.tar.gz"
        # Include only what's needed for Docker deployment
        import tarfile

        with tarfile.open(tarball, "w:gz") as tar:
            for item in [
                "pyproject.toml",
                "Dockerfile",
                "docker-compose.yml",
                "clanker",
                "ha_component",
                "config",
            ]:
                src = _PROJECT_ROOT / item
                if src.exists():
                    tar.add(src, arcname=item)

        # 3. SCP tarball to remote
        r = _run_scp(str(tarball), f"{host}:{install_dir}/clanker-deploy.tar.gz", timeout=120)
        steps.append({"step": "upload", **r})
        if not r["ok"]:
            return {"ok": False, "message": f"Upload failed: {r['stderr']}", "steps": steps}

    # 4. Extract on remote
    r = _run_ssh(
        host, f"cd {install_dir} && tar xzf clanker-deploy.tar.gz && rm clanker-deploy.tar.gz"
    )
    steps.append({"step": "extract", **r})
    if not r["ok"]:
        return {"ok": False, "message": "Extraction failed", "steps": steps}

    # 5. Install HA custom component
    r = _run_ssh(
        host,
        f"mkdir -p {ha_config_path}/custom_components && "
        f"cp -r {install_dir}/ha_component/custom_components/clanker "
        f"{ha_config_path}/custom_components/clanker",
    )
    steps.append({"step": "install_component", **r})
    if not r["ok"]:
        logger.warning("remote.component_install_failed", stderr=r["stderr"])

    # 6. Add clanker entry to HA configuration.yaml
    r = _run_ssh(
        host,
        f'grep -q "clanker:" {ha_config_path}/configuration.yaml 2>/dev/null || '
        f'echo -e \'\\nclanker:\\n  url: "http://localhost:8472"\' >> '
        f"{ha_config_path}/configuration.yaml",
    )
    steps.append({"step": "ha_config", **r})

    # 7. Start with docker-compose
    r = _run_ssh(
        host,
        f"cd {install_dir} && docker compose up -d --build 2>&1 "
        f"|| docker-compose up -d --build 2>&1",
        timeout=300,
    )
    steps.append({"step": "docker_start", **r})
    if not r["ok"]:
        return {"ok": False, "message": f"Docker start failed: {r['stderr']}", "steps": steps}

    return {
        "ok": True,
        "message": f"Clanker deployed to {host}:{install_dir} and started",
        "steps": steps,
    }


def install_component_ssh(
    host: str,
    ha_config_path: str = "/config",
) -> dict[str, Any]:
    """Install only the HA custom component to a remote host via SSH.

    Args:
        host: SSH destination.
        ha_config_path: Remote HA config directory.

    Returns:
        Dict with ``ok`` and ``message``.
    """
    component_src = _PROJECT_ROOT / "ha_component" / "custom_components" / "clanker"
    if not component_src.exists():
        return {"ok": False, "message": "Component source not found locally"}

    # Create directory
    r = _run_ssh(host, f"mkdir -p {ha_config_path}/custom_components")
    if not r["ok"]:
        return {"ok": False, "message": f"mkdir failed: {r['stderr']}"}

    # SCP the component
    r = _run_scp(
        str(component_src),
        f"{host}:{ha_config_path}/custom_components/clanker",
    )
    if not r["ok"]:
        return {"ok": False, "message": f"SCP failed: {r['stderr']}"}

    dst = f"{ha_config_path}/custom_components/clanker"
    return {"ok": True, "message": f"Component installed to {dst}"}
