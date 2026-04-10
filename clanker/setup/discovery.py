"""Home Assistant auto-discovery on the local network.

Tries common URLs, mDNS (homeassistant.local), and subnet scanning
to find a running HA instance.
"""

from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx


def _probe_url(url: str, timeout: float = 3.0) -> dict[str, Any] | None:
    """Try to reach HA at the given URL. Returns info dict or None."""
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{url.rstrip('/')}/api/")
            if resp.status_code in (200, 401):
                # 401 means HA is there but needs auth — still a valid discovery
                data = resp.json() if resp.status_code == 200 else {}
                return {
                    "url": url.rstrip("/"),
                    "version": data.get("version", "unknown"),
                    "auth_required": resp.status_code == 401,
                }
    except Exception:
        pass
    return None


def _resolve_mdns() -> str | None:
    """Try to resolve homeassistant.local via DNS."""
    try:
        ip = socket.gethostbyname("homeassistant.local")
        return ip
    except socket.gaierror:
        return None


def _get_local_subnet() -> str | None:
    """Guess the local subnet (e.g. '192.168.1')."""
    try:
        # Connect to a public IP (doesn't actually send data) to get local IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        parts = local_ip.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3])
    except Exception:
        pass
    return None


def discover_ha(
    *,
    scan_subnet: bool = True,
    extra_urls: list[str] | None = None,
    timeout: float = 3.0,
) -> list[dict[str, Any]]:
    """Auto-discover Home Assistant instances on the local network.

    Strategy:
    1. Try common well-known URLs (localhost, homeassistant.local)
    2. Resolve mDNS for homeassistant.local
    3. Optionally scan the local /24 subnet on port 8123

    Args:
        scan_subnet: Whether to scan the local subnet (slower but thorough).
        extra_urls: Additional URLs to probe.
        timeout: Per-probe timeout in seconds.

    Returns:
        List of discovered HA instances, each with ``url``, ``version``,
        ``auth_required``.
    """
    candidates: list[str] = [
        "http://localhost:8123",
        "http://homeassistant.local:8123",
        "http://homeassistant:8123",
    ]

    # mDNS resolution
    mdns_ip = _resolve_mdns()
    if mdns_ip:
        candidates.append(f"http://{mdns_ip}:8123")

    # Extra user-provided URLs
    if extra_urls:
        candidates.extend(extra_urls)

    # Subnet scan for port 8123
    if scan_subnet:
        subnet = _get_local_subnet()
        if subnet:
            # Quick port check before full HTTP probe
            for i in range(1, 255):
                ip = f"{subnet}.{i}"
                url = f"http://{ip}:8123"
                if url not in candidates:
                    candidates.append(url)

    # Deduplicate
    seen: set[str] = set()
    unique: list[str] = []
    for url in candidates:
        normalized = url.rstrip("/")
        if normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)

    # Probe in parallel (with priority: well-known first)
    found: list[dict[str, Any]] = []
    found_urls: set[str] = set()

    # Probe well-known first (fast)
    well_known = unique[:4]
    subnet_candidates = unique[4:]

    for url in well_known:
        result = _probe_url(url, timeout=timeout)
        if result and result["url"] not in found_urls:
            found.append(result)
            found_urls.add(result["url"])

    # If we already found HA, skip subnet scan
    if found or not scan_subnet:
        return found

    # Subnet scan in parallel (slower)
    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = {
            pool.submit(_probe_url, url, timeout): url
            for url in subnet_candidates
        }
        for future in as_completed(futures, timeout=timeout + 5):
            try:
                result = future.result()
                if result and result["url"] not in found_urls:
                    found.append(result)
                    found_urls.add(result["url"])
            except Exception:
                pass

    return found


def quick_discover(timeout: float = 3.0) -> dict[str, Any] | None:
    """Fast discovery — only tries well-known URLs, no subnet scan.

    Returns:
        First discovered HA instance, or None.
    """
    results = discover_ha(scan_subnet=False, timeout=timeout)
    return results[0] if results else None
