# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Shahab Nedaei
"""Self-provisioning of host backends the app needs (rootless).

Cloudy should "just work" without the user installing anything. For the
shipped Flatpak the rclone binary is bundled at build time (/app/bin). For other
installs, this module ensures rclone is available by downloading the official
static binary into a user-writable dir — no sudo, no system package manager,
checksum-verified.

We never invoke a system package manager or sudo: an app silently elevating on
someone's PC is exactly what we don't do.
"""

from __future__ import annotations

import hashlib
import io
import os
import platform
import shutil
import stat
import urllib.request
import zipfile
from pathlib import Path

from gi.repository import GLib

DOWNLOADS = "https://downloads.rclone.org"


def deps_bin_dir() -> Path:
    return Path(GLib.get_user_data_dir()) / "cloudy" / "bin"


def resolve(binary: str) -> str | None:
    """Find a backend binary: PATH first, then our provisioned dir."""
    found = shutil.which(binary)
    if found:
        return found
    local = deps_bin_dir() / binary
    return str(local) if local.exists() and os.access(local, os.X_OK) else None


def _host_nautilus_extension_dst() -> Path:
    return (Path.home() / ".local" / "share" / "nautilus-python"
            / "extensions" / "cloudy_nautilus.py")


def _nautilus_extension_source() -> Path | None:
    """Locate the bundled Nautilus extension across install layouts: Flatpak
    (/app), a meson/RPM prefix (share/nautilus-python next to share/cloudy), and
    the dev tree (nautilus-extension/)."""
    here = Path(__file__).resolve()
    # parents[3] is the install prefix's share/ (…/share/cloudy/cloudy/core →
    # share) OR, in the dev tree, the repo root (src/cloudy/core → repo).
    candidates = [
        Path("/app/share/nautilus-python/extensions/cloudy_nautilus.py"),
        here.parents[3] / "nautilus-python" / "extensions" / "cloudy_nautilus.py",
        here.parents[3] / "nautilus-extension" / "cloudy_nautilus.py",
    ]
    return next((p for p in candidates if p.exists()), None)


def set_host_nautilus_extension(enabled: bool, log=lambda _m: None) -> None:
    """Install or remove the per-user host Nautilus extension to match the
    ``nautilus-extension-enabled`` setting. Best-effort; never raises.

    ``enabled`` copies the bundled extension into the host's per-user extensions
    dir (the host file manager can't read ``/app`` inside Flatpak); disabling
    removes that copy. A system-wide RPM copy, if any, isn't touched."""
    dst = _host_nautilus_extension_dst()
    try:
        if enabled:
            src = _nautilus_extension_source()
            if src is None:
                log("Nautilus extension source not found")
                return
            new = src.read_bytes()
            if dst.exists() and dst.read_bytes() == new:
                return
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(new)
            log(f"Installed Nautilus extension to {dst}")
        elif dst.exists():
            dst.unlink()
            log(f"Removed Nautilus extension from {dst}")
    except OSError as exc:
        log(f"Nautilus extension toggle failed: {exc}")


def _rclone_arch() -> str:
    machine = platform.machine().lower()
    return {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine, "amd64")


def _fetch(url: str, timeout: int = 60) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def ensure_rclone(log=lambda _m: None) -> str:
    """Return a path to rclone, downloading it (rootless) if necessary."""
    existing = resolve("rclone")
    if existing:
        return existing

    arch = _rclone_arch()
    version = _fetch(f"{DOWNLOADS}/version.txt").decode().split()[-1]  # e.g. v1.71.0
    zip_name = f"rclone-{version}-linux-{arch}.zip"
    log(f"Downloading {zip_name}…")

    # Verify against the published SHA256SUMS for this version.
    sums = _fetch(f"{DOWNLOADS}/{version}/SHA256SUMS").decode()
    expected = None
    for line in sums.splitlines():
        if zip_name in line:
            expected = line.split()[0]
            break
    if expected is None:
        raise RuntimeError(f"no checksum found for {zip_name}")

    blob = _fetch(f"{DOWNLOADS}/{version}/{zip_name}")
    actual = hashlib.sha256(blob).hexdigest()
    if actual != expected:
        raise RuntimeError(f"checksum mismatch for {zip_name}")

    target_dir = deps_bin_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "rclone"
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        member = next(n for n in zf.namelist() if n.endswith("/rclone"))
        with zf.open(member) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    log(f"Installed rclone {version} to {target}")
    return str(target)
