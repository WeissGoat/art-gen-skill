# -*- coding: utf-8 -*-
"""Locate ai-image-gateway and its config without printing any secret."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

GATEWAY_REPO = "git@github.com:WeissGoat/ai-image-gateway.git"
PACKAGE = "ai_image_gateway"
_ENV_PATTERN = re.compile(r"\$\{(\w+)\}")

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _is_gateway_root(path: Path) -> bool:
    return (path / PACKAGE / "__init__.py").is_file()


def _git_root(start: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None


def _submodule_paths(repo: Path) -> list[Path]:
    gitmodules = repo / ".gitmodules"
    if not gitmodules.is_file():
        return []
    paths: list[Path] = []
    current_path = None
    for line in gitmodules.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("[submodule"):
            current_path = None
        elif line.startswith("path"):
            current_path = line.split("=", 1)[1].strip()
        elif line.startswith("url") and "ai-image-gateway" in line and current_path:
            paths.append(repo / current_path)
    return paths


def find_gateway(explicit: str | None = None, cwd: Path | None = None) -> tuple[Path | None, str]:
    """Return (root, source). Order: --root, env, project submodule/tools dir, installed package."""
    if explicit:
        p = Path(explicit).expanduser().resolve()
        return (p, "argument") if _is_gateway_root(p) else (None, f"argument_not_gateway:{p}")

    env = os.environ.get("AI_IMAGE_GATEWAY_ROOT")
    if env:
        p = Path(env).expanduser().resolve()
        if _is_gateway_root(p):
            return p, "env:AI_IMAGE_GATEWAY_ROOT"

    cwd = (cwd or Path.cwd()).resolve()
    repo = _git_root(cwd) or cwd
    candidates = _submodule_paths(repo) + [
        repo / "tools" / "ai-image-gateway",
        repo / "ai-image-gateway",
        repo.parent / "ai-image-gateway",
    ]
    for p in candidates:
        if _is_gateway_root(p):
            return p.resolve(), f"project:{p.relative_to(repo) if p.is_relative_to(repo) else p}"

    try:
        import importlib.util

        spec = importlib.util.find_spec(PACKAGE)
    except (ImportError, ValueError):
        spec = None
    if spec and spec.origin:
        p = Path(spec.origin).resolve().parent.parent
        if _is_gateway_root(p):
            return p, "installed_package"
    return None, "not_found"


def ensure_importable(root: Path) -> None:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def find_config(root: Path, explicit: str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser()
        return p.resolve() if p.is_file() else None
    env = os.environ.get("AI_IMAGE_GATEWAY_CONFIG")
    if env and Path(env).expanduser().is_file():
        return Path(env).expanduser().resolve()
    for name in ("config.local.yaml", "config.yaml"):
        if (root / name).is_file():
            return (root / name).resolve()
    return None


def git_commit(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%h %cs %s"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _value_state(value: Any) -> str:
    """'set', 'missing' or 'env_missing:NAME' — never the value itself."""
    if value is None or value == "":
        return "missing"
    if isinstance(value, str):
        names = _ENV_PATTERN.findall(value)
        missing = [n for n in names if not os.environ.get(n)]
        if missing:
            return "env_missing:" + ",".join(missing)
    return "set"


def summarize_config(path: Path) -> dict[str, Any]:
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    defaults = raw.get("default_provider") or {}
    providers = {}
    for name, cfg in (raw.get("providers") or {}).items():
        cfg = cfg or {}
        auth = cfg.get("auth") or {}
        settings = cfg.get("settings") or {}
        providers[name] = {
            "enabled": bool(cfg.get("enabled", True)),
            "model": settings.get("model", ""),
            "base_url_state": _value_state(settings.get("base_url")) if "base_url" in settings else "n/a",
            "auth": {k: _value_state(v) for k, v in auth.items()},
        }
    return {"default_provider": defaults, "providers": providers}
