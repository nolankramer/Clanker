"""Temporary SSH key management for remote setup.

Generates a temporary ed25519 key pair so the user can paste the
public key into the HA SSH add-on's authorized_keys config. The
private key is used for all setup SSH operations and cleaned up
after setup completes.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

_KEY_DIR: Path | None = None
_KEY_PATH: Path | None = None


def get_or_create_setup_key() -> dict[str, str]:
    """Generate a temporary SSH key pair for setup.

    Returns:
        Dict with ``private_key_path`` and ``public_key`` (the text
        to paste into HA SSH add-on config).
    """
    global _KEY_DIR, _KEY_PATH

    if _KEY_PATH and _KEY_PATH.exists():
        pub = _KEY_PATH.with_suffix(".pub").read_text().strip()
        return {"private_key_path": str(_KEY_PATH), "public_key": pub}

    _KEY_DIR = Path(tempfile.mkdtemp(prefix="clanker-ssh-"))
    _KEY_PATH = _KEY_DIR / "clanker_setup_key"

    subprocess.run(
        [
            "ssh-keygen", "-t", "ed25519",
            "-f", str(_KEY_PATH),
            "-N", "",  # no passphrase
            "-C", "clanker-setup-temporary",
        ],
        capture_output=True,
        check=True,
    )

    # Restrict permissions (required by SSH)
    os.chmod(_KEY_PATH, 0o600)

    pub = _KEY_PATH.with_suffix(".pub").read_text().strip()
    return {"private_key_path": str(_KEY_PATH), "public_key": pub}


def get_ssh_key_args() -> list[str]:
    """Get SSH args to use the temporary key (if it exists).

    Returns:
        List of SSH args like ["-i", "/tmp/.../key"] or empty list.
    """
    if _KEY_PATH and _KEY_PATH.exists():
        return ["-i", str(_KEY_PATH)]
    return []


def cleanup_setup_key() -> None:
    """Remove the temporary SSH key pair."""
    global _KEY_DIR, _KEY_PATH

    if _KEY_PATH and _KEY_PATH.exists():
        _KEY_PATH.unlink(missing_ok=True)
        _KEY_PATH.with_suffix(".pub").unlink(missing_ok=True)
    if _KEY_DIR and _KEY_DIR.exists():
        _KEY_DIR.rmdir()
    _KEY_DIR = None
    _KEY_PATH = None
