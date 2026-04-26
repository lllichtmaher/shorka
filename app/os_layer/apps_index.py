"""Cached index of installed Windows apps via PowerShell `Get-StartApps`.

Each entry has `Name` and `AppID` (AUMID). Launch with `explorer.exe shell:AppsFolder\\<aumid>`.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

from ..config import settings


CACHE_TTL_SEC = 24 * 3600


def _refresh_cache() -> list[dict[str, Any]]:
    proc = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-StartApps | ConvertTo-Json -Compress",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Get-StartApps failed: {proc.stderr.strip()}")
    raw = proc.stdout.strip()
    if not raw:
        return []
    apps = json.loads(raw)
    if isinstance(apps, dict):
        apps = [apps]
    cache_path: Path = settings.apps_index_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"ts": time.time(), "apps": apps}), encoding="utf-8")
    return apps


def load(force_refresh: bool = False) -> list[dict[str, Any]]:
    cache_path: Path = settings.apps_index_path
    if not force_refresh and cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if time.time() - float(data["ts"]) < CACHE_TTL_SEC:
                return list(data["apps"])
        except Exception:
            pass
    return _refresh_cache()


def find(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Top fuzzy matches for `query` against installed app names."""
    apps = load()
    if not apps:
        return []
    names = [a.get("Name", "") for a in apps]
    matches = process.extract(query, names, scorer=fuzz.WRatio, limit=limit, score_cutoff=50)
    return [apps[i] for _, _, i in matches]


def launch(aumid: str) -> None:
    """Launch a UWP/Win32/Store app by AUMID."""
    subprocess.Popen(
        ["explorer.exe", f"shell:AppsFolder\\{aumid}"],
        shell=False,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
    )
