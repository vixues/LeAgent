"""Install Python packages declared by an Agent Skill into the backend interpreter env.

Skills may declare dependencies via:

- ``requirements.txt`` or ``requirements-skills.txt`` at the skill root
- ``[project].dependencies`` in ``pyproject.toml`` (PEP 621)
- ``metadata.leagent.python_dependencies`` in SKILL.md frontmatter (list of PEP 508 specs)

Installation uses ``uv pip install --python <resolved backend Python>`` when ``uv`` is on PATH.
Fingerprint caching skips redundant installs until declarations change.
"""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import structlog

from leagent.services.python_env.resolve import resolve_backend_python_executable
from leagent.skills.base import Skill

logger = structlog.get_logger(__name__)

_REQUIREMENTS_NAMES = ("requirements.txt", "requirements-skills.txt")

# Process-local cache: (skill root resolved, python exe resolved) -> fingerprint hex
_installed_fingerprint: dict[tuple[str, str], str] = {}


def clear_skill_python_deps_cache() -> None:
    """Testing hook — drop fingerprint cache."""
    _installed_fingerprint.clear()


async def run_uv_pip_install(
    *,
    python_executable: str,
    packages: Sequence[str],
    requirements_file: Path | None = None,
    timeout_sec: float,
) -> dict[str, Any]:
    """Run ``uv pip install --python <exe>`` (optional ``-r`` file + PEP 508 specs).

    Returns a dict with ``ok`` (bool), optional ``error``, ``returncode``, ``stdout``, ``stderr``.
    Does not read settings — callers enforce policy.
    """
    specs = [s.strip() for s in packages if isinstance(s, str) and s.strip()]
    if not specs and (requirements_file is None or not requirements_file.is_file()):
        return {
            "ok": False,
            "error": "Nothing to install: provide at least one package or a readable requirements file.",
        }

    uv = shutil.which("uv")
    if not uv:
        return {
            "ok": False,
            "error": "uv not found on PATH; install uv (https://docs.astral.sh/uv/) or add packages to the backend environment manually.",
        }

    argv: list[str] = [uv, "pip", "install", "--python", python_executable]
    if requirements_file is not None:
        argv.extend(["-r", str(requirements_file)])
    argv.extend(list(dict.fromkeys(specs)))

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return {"ok": False, "error": f"failed to spawn uv: {exc}"}

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except TimeoutError:
        proc.kill()
        return {
            "ok": False,
            "error": f"uv pip install timed out after {timeout_sec}s",
        }

    stdout = stdout_b.decode("utf-8", errors="replace")[-40_000:]
    stderr = stderr_b.decode("utf-8", errors="replace")[-40_000:]
    if proc.returncode != 0:
        logger.warning(
            "uv_pip_install_failed",
            returncode=proc.returncode,
            stderr_preview=stderr[:500],
        )
        return {
            "ok": False,
            "error": "uv pip install failed",
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    return {
        "ok": True,
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def _metadata_python_specs(skill: Skill) -> list[str]:
    meta = skill.manifest.metadata.get("leagent") if skill.manifest.metadata else None
    if not isinstance(meta, dict):
        return []
    raw = meta.get("python_dependencies")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [line.strip() for line in raw.splitlines() if line.strip()]
    if isinstance(raw, (list, tuple)):
        out: list[str] = []
        for item in raw:
            if not item:
                continue
            spec = str(item).strip()
            if spec:
                out.append(spec)
        return out
    return []


def _pyproject_dependencies(skill_root: Path) -> list[str]:
    pp = skill_root / "pyproject.toml"
    if not pp.is_file():
        return []
    try:
        data = pp.read_bytes()
    except OSError:
        return []
    try:
        import tomllib

        parsed = tomllib.loads(data.decode("utf-8"))
    except Exception:
        return []
    project = parsed.get("project")
    if not isinstance(project, dict):
        return []
    deps = project.get("dependencies")
    if not isinstance(deps, list):
        return []
    out: list[str] = []
    for d in deps:
        if isinstance(d, str) and d.strip():
            out.append(d.strip())
    return out


def _requirements_path(skill_root: Path) -> Path | None:
    for name in _REQUIREMENTS_NAMES:
        p = skill_root / name
        if p.is_file():
            return p
    return None


def _fingerprint(skill_root: Path, skill: Skill) -> str:
    parts: list[bytes] = []
    req = _requirements_path(skill_root)
    if req:
        try:
            parts.append(req.read_bytes())
        except OSError as exc:
            parts.append(f"req_err:{exc}".encode())
    specs = sorted(_metadata_python_specs(skill))
    parts.append("\n".join(specs).encode("utf-8"))
    pyp = sorted(_pyproject_dependencies(skill_root))
    parts.append("\n".join(pyp).encode("utf-8"))
    h = hashlib.sha256()
    for chunk in parts:
        h.update(chunk)
        h.update(b"\0")
    return h.hexdigest()


def _has_any_declaration(skill_root: Path, skill: Skill) -> bool:
    req = _requirements_path(skill_root)
    if req:
        try:
            if req.stat().st_size > 0:
                return True
        except OSError:
            return True
    if _metadata_python_specs(skill):
        return True
    return bool(_pyproject_dependencies(skill_root))


async def ensure_skill_python_deps(skill: Skill) -> dict[str, Any]:
    """Ensure declared packages are installed for ``skill`` using uv.

    Returns a dict with ``ok`` (bool), optional ``message``, ``skipped`` (bool),
    ``installed`` (bool), ``stderr`` / ``stdout`` from uv when run.
    """
    from leagent.config.settings import get_settings

    settings = get_settings()
    if not settings.skill_python_deps_auto_install:
        return {"ok": True, "skipped": True, "reason": "skill_python_deps_auto_install_disabled"}

    root = skill.path
    if not root:
        return {"ok": True, "skipped": True, "reason": "skill_has_no_path"}

    try:
        skill_root = root.resolve()
    except OSError as exc:
        return {"ok": False, "skipped": False, "error": f"invalid skill path: {exc}"}

    if not _has_any_declaration(skill_root, skill):
        return {"ok": True, "skipped": True, "reason": "no_python_dependency_declarations"}

    py_resolved = resolve_backend_python_executable()

    fp = _fingerprint(skill_root, skill)
    cache_key = (str(skill_root), py_resolved)
    if _installed_fingerprint.get(cache_key) == fp:
        return {"ok": True, "skipped": True, "reason": "already_synced", "fingerprint": fp}

    req_path = _requirements_path(skill_root)
    extra_specs = list(dict.fromkeys(_metadata_python_specs(skill) + _pyproject_dependencies(skill_root)))

    timeout = float(settings.skill_python_deps_install_timeout_sec)
    logger.info(
        "skill_python_deps_uv_install",
        skill=skill.name,
        skill_root=str(skill_root),
        has_requirements=bool(req_path),
        extra_specs_count=len(extra_specs),
    )

    result = await run_uv_pip_install(
        python_executable=py_resolved,
        packages=extra_specs,
        requirements_file=req_path,
        timeout_sec=timeout,
    )
    if not result.get("ok"):
        err = str(result.get("error") or "uv pip install failed")
        logger.warning(
            "skill_python_deps_failed",
            skill=skill.name,
            error=err[:500],
        )
        return {
            "ok": False,
            "skipped": False,
            "error": err,
            "returncode": result.get("returncode"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
        }

    _installed_fingerprint[cache_key] = fp
    logger.info("skill_python_deps_ok", skill=skill.name, fingerprint=fp[:16])
    return {
        "ok": True,
        "skipped": False,
        "installed": True,
        "fingerprint": fp,
        "stdout": str(result.get("stdout") or ""),
        "stderr": str(result.get("stderr") or ""),
    }
