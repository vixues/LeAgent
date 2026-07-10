"""OS-level sandbox wrapping for subprocess execution.

Codex-style kernel-enforced boundaries: instead of relying purely on
binary whitelists and path ACL conventions, subprocess argv can be
wrapped with a platform sandbox so the *kernel* blocks out-of-bounds
writes and (where supported) network access.

Platforms:

* **Linux** — `bubblewrap <https://github.com/containers/bubblewrap>`_
  (``bwrap``): read-only root, explicit writable bind mounts, optional
  network namespace isolation. Availability is probed once per process
  (AppArmor on Ubuntu 24.04+ may block user namespaces; ``--unshare-net``
  may fail loopback setup) and each failing feature degrades gracefully
  with a structured warning — the same strategy Codex CLI uses.
* **macOS** — Seatbelt via ``/usr/bin/sandbox-exec`` with a generated
  profile (deny file-write except allowed subpaths, optional deny
  network).
* **Windows** — no wrapper yet; always degrades to direct execution.

The wrapper is *opt-out safe*: any probe failure returns the original
argv untouched so existing deployments keep working, with the applied /
degraded state recorded in the returned :class:`SandboxApplication`.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

#: Recognised sandbox modes (mirrors Codex `sandbox_mode`).
MODE_NONE = "none"
MODE_READ_ONLY = "read-only"
MODE_WORKSPACE_WRITE = "workspace-write"
MODE_FULL = "danger-full-access"

_VALID_MODES = {MODE_NONE, MODE_READ_ONLY, MODE_WORKSPACE_WRITE, MODE_FULL}


@dataclass(frozen=True)
class SandboxSpec:
    """Declarative description of the sandbox for one subprocess."""

    mode: str = MODE_NONE
    writable_roots: tuple[str, ...] = ()
    network_access: bool = True

    def __post_init__(self) -> None:
        if self.mode not in _VALID_MODES:
            raise ValueError(
                f"Unknown sandbox mode {self.mode!r}; expected one of {sorted(_VALID_MODES)}"
            )

    @property
    def wants_wrapper(self) -> bool:
        return self.mode in (MODE_READ_ONLY, MODE_WORKSPACE_WRITE)


@dataclass
class SandboxApplication:
    """Result of attempting to wrap an argv."""

    argv: list[str]
    applied: bool = False
    backend: str = "none"  # "bwrap" | "seatbelt" | "none"
    degraded_reasons: list[str] = field(default_factory=list)
    network_isolated: bool = False

    def to_metadata(self) -> dict[str, object]:
        return {
            "sandbox_applied": self.applied,
            "sandbox_backend": self.backend,
            "sandbox_network_isolated": self.network_isolated,
            "sandbox_degraded": list(self.degraded_reasons),
        }


def resolve_sandbox_mode(explicit: str | None = None) -> str:
    """Resolve the effective sandbox mode.

    Precedence: explicit argument > ``LEAGENT_SANDBOX_MODE`` env >
    ``settings.code_execution_isolation_mode`` > ``none``.

    The legacy isolation values map: ``none``→none, ``auto``→
    workspace-write (best effort), ``bwrap``→workspace-write.
    """
    raw = (explicit or "").strip().lower()
    if not raw or raw == "auto":
        raw = os.environ.get("LEAGENT_SANDBOX_MODE", "").strip().lower()
    if not raw or raw == "auto":
        try:
            from leagent.config.settings import get_settings

            raw = (get_settings().code_execution_isolation_mode or "").strip().lower()
        except Exception:  # noqa: BLE001
            raw = ""
    if raw in ("", "auto"):
        return MODE_NONE
    if raw in ("bwrap", "workspace_write", "workspace-write"):
        return MODE_WORKSPACE_WRITE
    if raw in ("read_only", "read-only", "ro"):
        return MODE_READ_ONLY
    if raw in ("full", "danger-full-access", "danger_full_access"):
        return MODE_FULL
    if raw in _VALID_MODES:
        return raw
    logger.warning("sandbox_mode_unknown", value=raw)
    return MODE_NONE


def default_writable_roots(workspace: str | None) -> tuple[str, ...]:
    """Standard writable set: the workspace plus the system temp dir."""
    roots: list[str] = []
    if workspace:
        roots.append(str(Path(workspace).resolve()))
    roots.append(tempfile.gettempdir())
    return tuple(dict.fromkeys(roots))


# ---------------------------------------------------------------------------
# Capability probing (cached per process, like Codex's startup probe)
# ---------------------------------------------------------------------------


def _run_probe(argv: list[str]) -> bool:
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5.0,
            check=False,
        )
        return proc.returncode == 0
    except Exception:  # noqa: BLE001
        return False


@functools.lru_cache(maxsize=1)
def bwrap_path() -> str | None:
    return shutil.which("bwrap")


@functools.lru_cache(maxsize=1)
def probe_bwrap_basic() -> bool:
    """Can bwrap create a basic ro-root sandbox on this host?"""
    bw = bwrap_path()
    if not bw or not sys.platform.startswith("linux"):
        return False
    ok = _run_probe(
        [bw, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--", "/bin/true"]
    )
    if not ok:
        logger.warning(
            "sandbox_bwrap_unavailable",
            hint=(
                "bwrap exists but cannot create a sandbox (AppArmor "
                "user-namespace restriction?). Falling back to direct "
                "execution. See docs: load the bwrap-userns-restrict "
                "AppArmor profile or set "
                "kernel.apparmor_restrict_unprivileged_userns=0."
            ),
        )
    return ok


@functools.lru_cache(maxsize=1)
def probe_bwrap_network_isolation() -> bool:
    """Can bwrap additionally unshare the network namespace?"""
    bw = bwrap_path()
    if not bw or not probe_bwrap_basic():
        return False
    ok = _run_probe(
        [
            bw, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
            "--unshare-net", "--", "/bin/true",
        ]
    )
    if not ok:
        logger.warning(
            "sandbox_bwrap_no_netns",
            hint=(
                "bwrap works but --unshare-net failed (loopback "
                "RTM_NEWADDR restriction). Commands run sandboxed for "
                "the filesystem but WITHOUT network isolation."
            ),
        )
    return ok


@functools.lru_cache(maxsize=1)
def seatbelt_path() -> str | None:
    if sys.platform != "darwin":
        return None
    p = "/usr/bin/sandbox-exec"
    return p if os.path.exists(p) else None


def reset_probe_cache() -> None:
    """Testing hook: clear cached probes."""
    bwrap_path.cache_clear()
    probe_bwrap_basic.cache_clear()
    probe_bwrap_network_isolation.cache_clear()
    seatbelt_path.cache_clear()


# ---------------------------------------------------------------------------
# Wrapping
# ---------------------------------------------------------------------------


def _git_ro_binds(root: Path) -> list[str]:
    """Keep `.git` read-only inside writable roots (Codex Seatbelt parity)."""
    args: list[str] = []
    git_dir = root / ".git"
    if git_dir.exists():
        args += ["--ro-bind", str(git_dir), str(git_dir)]
    return args


def _build_bwrap_argv(
    argv: list[str],
    spec: SandboxSpec,
    *,
    cwd: str,
) -> tuple[list[str], bool]:
    """Return (wrapped argv, network_isolated)."""
    bw = bwrap_path()
    assert bw is not None
    wrapped: list[str] = [
        bw,
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/run",
        "--die-with-parent",
        "--chdir", cwd,
    ]
    if spec.mode == MODE_WORKSPACE_WRITE:
        for raw in spec.writable_roots:
            root = Path(raw)
            if not root.exists():
                continue
            wrapped += ["--bind", str(root), str(root)]
            wrapped += _git_ro_binds(root)
    network_isolated = False
    if not spec.network_access and probe_bwrap_network_isolation():
        wrapped.append("--unshare-net")
        network_isolated = True
    wrapped.append("--")
    wrapped.extend(argv)
    return wrapped, network_isolated


def _seatbelt_profile(spec: SandboxSpec) -> str:
    lines = [
        "(version 1)",
        "(allow default)",
        "(deny file-write*)",
        '(allow file-write* (subpath "/private/tmp") (subpath "/private/var/tmp") (subpath "/dev"))',
    ]
    if spec.mode == MODE_WORKSPACE_WRITE:
        for raw in spec.writable_roots:
            root = Path(raw)
            if root.exists():
                lines.append(f'(allow file-write* (subpath "{root}"))')
                git_dir = root / ".git"
                if git_dir.exists():
                    lines.append(f'(deny file-write* (subpath "{git_dir}"))')
    if not spec.network_access:
        lines.append("(deny network*)")
    return "\n".join(lines) + "\n"


def _build_seatbelt_argv(
    argv: list[str],
    spec: SandboxSpec,
) -> tuple[list[str], bool]:
    sb = seatbelt_path()
    assert sb is not None
    profile = _seatbelt_profile(spec)
    tmp = tempfile.NamedTemporaryFile(
        "w", suffix=".sb", prefix="leagent-sandbox-", delete=False,
    )
    with tmp:
        tmp.write(profile)
    return [sb, "-f", tmp.name, *argv], not spec.network_access


def wrap_argv(
    argv: list[str],
    spec: SandboxSpec,
    *,
    cwd: str,
) -> SandboxApplication:
    """Wrap ``argv`` in the platform sandbox described by ``spec``.

    Never raises for capability problems: on any probe failure the
    original argv is returned with ``applied=False`` plus a degradation
    reason, mirroring Codex's fall-back-with-warning behaviour.
    """
    if not argv:
        return SandboxApplication(argv=list(argv))
    if not spec.wants_wrapper:
        return SandboxApplication(argv=list(argv))

    if sys.platform.startswith("linux"):
        if not bwrap_path():
            return SandboxApplication(
                argv=list(argv),
                degraded_reasons=["bwrap not installed"],
            )
        if not probe_bwrap_basic():
            return SandboxApplication(
                argv=list(argv),
                degraded_reasons=["bwrap unusable on this host (userns restriction?)"],
            )
        wrapped, net_isolated = _build_bwrap_argv(argv, spec, cwd=cwd)
        app = SandboxApplication(
            argv=wrapped,
            applied=True,
            backend="bwrap",
            network_isolated=net_isolated,
        )
        if not spec.network_access and not net_isolated:
            app.degraded_reasons.append("network isolation unavailable (--unshare-net failed)")
        return app

    if sys.platform == "darwin":
        if not seatbelt_path():
            return SandboxApplication(
                argv=list(argv),
                degraded_reasons=["sandbox-exec not found"],
            )
        try:
            wrapped, net_isolated = _build_seatbelt_argv(argv, spec)
        except OSError as exc:
            return SandboxApplication(
                argv=list(argv),
                degraded_reasons=[f"seatbelt profile write failed: {exc}"],
            )
        return SandboxApplication(
            argv=wrapped,
            applied=True,
            backend="seatbelt",
            network_isolated=net_isolated,
        )

    return SandboxApplication(
        argv=list(argv),
        degraded_reasons=[f"no sandbox backend for platform {sys.platform!r}"],
    )
