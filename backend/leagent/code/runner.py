"""Stdlib entrypoint executed inside the sandbox subprocess.

Invoked as ``python -m leagent.code.runner``. The
parent process streams a payload on stdin describing the
script to run, the user-supplied globals, and limits. Two encodings:

* **V2 framed** (preferred): ``LEAGENT_RUNNER_V2`` line, JSON metadata line
  (all keys except ``source``), a decimal UTF-8 byte length line, then raw
  UTF-8 source bytes. Built by :func:`build_runner_stdin`.
* **Legacy**: a single JSON object (``source`` embedded as a JSON string).

This module:

1. Installs a SIGALRM timer as a last-resort hard stop.
2. ``chdir``'s into the provided workspace directory.
3. Executes the source with full builtins plus the requested globals.
4. Emits a single NDJSON-terminated response on stdout containing
   ``status``, ``stdout``, ``stderr``, ``result`` (if JSON-serialisable),
   ``produced_files`` (paths relative to the workspace), and timing.
"""

from __future__ import annotations

import io
import json
import mimetypes
import os
import signal
import sys
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any


_STDOUT_LIMIT = 1 << 20  # 1 MB
_RESULT_STR_LIMIT = 64 * 1024  # 64 KB textual result


def _on_alarm(signum: int, frame: Any) -> None:
    raise TimeoutError("wall-clock timeout inside sandboxed code")


def _safe_json(obj: Any) -> Any:
    """Return ``obj`` if JSON-serialisable, else its ``repr``."""
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return repr(obj)[:_RESULT_STR_LIMIT]


def _guess_mime(path: Path) -> str | None:
    mime, _ = mimetypes.guess_type(str(path))
    return mime


def _scan_files(base: Path) -> set[Path]:
    """Return a set of resolved file paths under *base* (best-effort)."""
    out: set[Path] = set()
    if not base.exists():
        return out
    for path in base.rglob("*"):
        try:
            if path.is_file():
                out.add(path)
        except OSError:
            continue
    return out


def _listing(
    base: Path,
    before: set[Path],
    *,
    extra_roots: list[Path] | None = None,
    extra_before: dict[Path, set[Path]] | None = None,
) -> list[dict[str, Any]]:
    """Diff workspace + extra roots against their pre-execution snapshots.

    Files inside *base* are reported with **relative** paths (legacy behaviour).
    Files inside *extra_roots* are reported with **absolute** paths so the
    parent controller can ingest them via ``register_external_file``.
    """
    produced: list[dict[str, Any]] = []
    seen: set[Path] = set()

    def _emit(path: Path, *, root: Path | None) -> None:
        if path in seen:
            return
        seen.add(path)
        try:
            size = path.stat().st_size
        except OSError:
            return
        mime = _guess_mime(path)
        if root is not None and root == base:
            try:
                rel = str(path.relative_to(root))
            except ValueError:
                rel = str(path)
            entry: dict[str, Any] = {"path": rel, "bytes": size}
        else:
            entry = {"path": str(path), "bytes": size}
        if mime:
            entry["mime"] = mime
        produced.append(entry)

    if base.exists():
        for path in base.rglob("*"):
            try:
                if not path.is_file():
                    continue
            except OSError:
                continue
            if path in before:
                continue
            _emit(path, root=base)

    for root in extra_roots or []:
        if not root.exists():
            continue
        snapshot = (extra_before or {}).get(root, set())
        for path in root.rglob("*"):
            try:
                if not path.is_file():
                    continue
            except OSError:
                continue
            if path in snapshot:
                continue
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            try:
                if resolved.is_relative_to(base):
                    continue
            except (AttributeError, ValueError):
                pass
            _emit(path, root=root)

    return produced


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _sandbox_builtins(*, workspace_path: Path) -> dict[str, Any]:
    """Full builtins for user ``exec`` — no import restrictions."""
    import builtins

    out = dict(builtins.__dict__)
    out["__name__"] = "__sandbox__"
    return out


def _configure_matplotlib_if_needed(source: str, base: Path) -> None:
    markers = (
        "matplotlib",
        "pyplot",
        "plt.",
        "font_manager",
        "mpl.",
        "pylab",
    )
    if not any(m in source for m in markers):
        return
    os.environ.setdefault("MPLBACKEND", "Agg")
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception:
        return

    try:
        from leagent.code.matplotlib_cjk import configure_matplotlib_cjk

        configure_matplotlib_cjk()
    except Exception:
        pass

    def _show(*args: Any, **kwargs: Any) -> None:
        if not plt.get_fignums():
            return
        target = base / f"figure_{int(time.time() * 1000)}.png"
        plt.savefig(target, dpi=150, bbox_inches="tight")

    plt.show = _show  # type: ignore[assignment]


_RUNNER_V2_MAGIC = b"LEAGENT_RUNNER_V2\n"


def build_runner_stdin(payload: dict[str, Any]) -> bytes:
    """Build V2 stdin: magic + JSON meta (no ``source``) + length + raw UTF-8 body."""
    source = payload.get("source", "")
    if not isinstance(source, str):
        source = str(source)
    src_b = source.encode("utf-8")
    meta = {k: v for k, v in payload.items() if k != "source"}
    meta["runner_protocol"] = 2
    return (
        _RUNNER_V2_MAGIC
        + json.dumps(meta, ensure_ascii=False).encode("utf-8")
        + b"\n"
        + str(len(src_b)).encode("ascii")
        + b"\n"
        + src_b
    )


def _load_runner_payload(raw: bytes) -> dict[str, Any]:
    if raw.startswith(_RUNNER_V2_MAGIC):
        rest = raw[len(_RUNNER_V2_MAGIC) :]
        nl = rest.find(b"\n")
        if nl < 0:
            raise ValueError("missing metadata JSON after LEAGENT_RUNNER_V2")
        meta = json.loads(rest[:nl].decode("utf-8"))
        tail = rest[nl + 1 :]
        nl2 = tail.find(b"\n")
        if nl2 < 0:
            raise ValueError("missing source byte length line")
        n = int(tail[:nl2].decode("ascii").strip())
        body = tail[nl2 + 1 :]
        if len(body) != n:
            raise ValueError(
                f"source length mismatch: expected {n} bytes, got {len(body)}",
            )
        out: dict[str, Any] = dict(meta)
        out["source"] = body.decode("utf-8")
        return out
    return json.loads(raw.decode("utf-8"))


def main() -> int:
    try:
        raw_in = sys.stdin.buffer.read()
        payload = _load_runner_payload(raw_in)
    except Exception as exc:  # noqa: BLE001
        json.dump({"status": "error", "error": f"bad payload: {exc}"}, sys.stdout)
        sys.stdout.write("\n")
        return 2

    source = payload.get("source", "")
    globals_in = payload.get("globals", {}) or {}
    timeout_sec = float(payload.get("timeout_sec", 30.0))
    workspace = payload.get("workspace")
    extra_scan_roots_raw = payload.get("extra_scan_roots") or []

    if workspace:
        base = Path(workspace)
        base.mkdir(parents=True, exist_ok=True)
        os.chdir(base)
    else:
        base = Path.cwd()

    extra_roots: list[Path] = []
    seen_roots: set[Path] = set()
    for raw in extra_scan_roots_raw:
        if not raw:
            continue
        try:
            candidate = Path(str(raw)).expanduser().resolve()
        except OSError:
            continue
        try:
            if candidate == base or candidate.is_relative_to(base):
                continue
        except (AttributeError, ValueError):
            pass
        if candidate in seen_roots:
            continue
        seen_roots.add(candidate)
        extra_roots.append(candidate)

    os.environ.setdefault("MPLBACKEND", "Agg")
    _configure_matplotlib_if_needed(source, base)
    before = _scan_files(base)
    extra_before: dict[Path, set[Path]] = {
        root: _scan_files(root) for root in extra_roots
    }

    started = time.monotonic()
    use_alarm = hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")
    if use_alarm:
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.setitimer(signal.ITIMER_REAL, timeout_sec)

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    status = "ok"
    error_msg: str | None = None
    result_val: Any = None

    globals_env: dict[str, Any] = {
        "__name__": "__sandbox__",
        "__builtins__": _sandbox_builtins(workspace_path=base),
    }
    globals_env.update(globals_in)

    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exec(compile(source, "<sandbox>", "exec"), globals_env)  # noqa: S102
        result_val = globals_env.get("result")
    except TimeoutError as exc:
        status = "timeout"
        error_msg = str(exc) or "timeout"
    except MemoryError:
        status = "memory"
        error_msg = "memory limit exceeded"
    except BaseException as exc:  # noqa: BLE001 — surfaced to caller
        status = "error"
        error_msg = f"{type(exc).__name__}: {exc}"
        stderr_buf.write("\n" + traceback.format_exc())
    finally:
        if use_alarm:
            signal.setitimer(signal.ITIMER_REAL, 0)

    duration_ms = int((time.monotonic() - started) * 1000)
    stdout_text, stdout_trunc = _truncate(stdout_buf.getvalue(), _STDOUT_LIMIT)
    stderr_text, stderr_trunc = _truncate(stderr_buf.getvalue(), _STDOUT_LIMIT)

    envelope = {
        "status": status,
        "error": error_msg,
        "stdout": stdout_text,
        "stdout_truncated": stdout_trunc,
        "stderr": stderr_text,
        "stderr_truncated": stderr_trunc,
        "result": _safe_json(result_val),
        "produced_files": _listing(
            base,
            before,
            extra_roots=extra_roots,
            extra_before=extra_before,
        ),
        "duration_ms": duration_ms,
    }
    json.dump(envelope, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
