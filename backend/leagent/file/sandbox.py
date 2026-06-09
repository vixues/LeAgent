"""Filesystem path resolution for tool execution.

The sandbox has two jobs:

* turn model-friendly references (bare filenames, ``@file:``,
  ``@knowledge:``, attachment IDs) into concrete paths, and
* prove the resulting path belongs to a configured or per-request root.

Desktop/local deployments get wider default roots when
``LEAGENT_TOOL_FILE_ROOTS`` is not set, but path decisions still flow
through the same allow-list machinery used by server deployments.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

import structlog

from leagent.file.primitives import is_path_inside

if TYPE_CHECKING:
    from leagent.tools.base import ToolContext

logger = structlog.get_logger(__name__)

_UUID_36_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
    re.IGNORECASE,
)


def _lookup_attachment_id_path(
    lookup_by_id: dict[str, str],
    key: str | None,
) -> str | None:
    """Resolve *key* in *lookup_by_id* with case-insensitive UUID matching."""
    if not key:
        return None
    k = key.strip()
    if not k:
        return None
    if k in lookup_by_id:
        return lookup_by_id[k]
    lowered = k.lower()
    for existing_id, path in lookup_by_id.items():
        if existing_id.lower() == lowered:
            return path
    return None


def _resolve_path(raw: str | Path, *, strict: bool = False) -> Path:
    """Best-effort absolute path normalisation with consistent exceptions."""
    try:
        return Path(raw).expanduser().resolve(strict=strict)
    except (OSError, RuntimeError, ValueError) as exc:
        raise PermissionError(f"Invalid path: {raw!s}") from exc


def _dedupe_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    out: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return tuple(out)


def _is_user_home_path(raw: str) -> bool:
    """Return whether *raw* is an explicit user-home path like ``~/file``."""
    return raw == "~" or raw.startswith("~/")


def _split_configured_roots(raw: str) -> tuple[str, ...]:
    text = raw.strip()
    if not text:
        return ()
    if "," in text:
        parts = text.split(",")
    else:
        parts = text.split(os.pathsep)
    return tuple(part.strip() for part in parts if part.strip())


def _default_upload_root() -> str:
    for key in ("LEAGENT_FILES_UPLOAD_DIR", "FILES_UPLOAD_DIR"):
        value = os.environ.get(key)
        if value and value.strip():
            return value.strip()
    try:
        from leagent.config.settings import get_settings

        return get_settings().files.upload_dir
    except Exception:  # noqa: BLE001
        return "/var/lib/leagent/files"


def _knowledge_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    for key in ("LEAGENT_KNOWLEDGE_DIR", "FILES_KNOWLEDGE_STORAGE_DIR"):
        value = os.environ.get(key)
        if value and value.strip():
            base = _resolve_path(value.strip())
            roots.extend((base, base / "documents"))
            return _dedupe_paths(roots)
    try:
        from leagent.config.settings import get_settings

        base = _resolve_path(get_settings().files.resolved_knowledge_storage_dir())
        roots.extend((base, base / "documents"))
    except Exception:  # noqa: BLE001
        pass
    return _dedupe_paths(roots)


def _openclaw_root() -> Path | None:
    """Return the OpenClaw home directory used by installed interop skills."""
    value = os.environ.get("OPENCLAW_HOME")
    try:
        if value and value.strip():
            return _resolve_path(value.strip())
        return _resolve_path(Path.home() / ".openclaw")
    except PermissionError:
        return None


def _local_profile_roots() -> tuple[Path, ...]:
    try:
        from leagent.config.constants import LEAGENT_HOME, WORKING_DIR
        from leagent.config.settings import get_settings

        if not get_settings().is_single_machine_profile:
            return ()
        roots = [
            _resolve_path(LEAGENT_HOME),
            _resolve_path(WORKING_DIR),
            _resolve_path(Path.cwd()),
        ]
        openclaw = _openclaw_root()
        if openclaw is not None:
            roots.append(openclaw)
        return _dedupe_paths(roots)
    except Exception:  # noqa: BLE001
        roots = [_resolve_path(Path.cwd())]
        openclaw = _openclaw_root()
        if openclaw is not None:
            roots.append(openclaw)
        return _dedupe_paths(roots)


def _parse_roots() -> tuple[Path, ...]:
    """Return process-wide roots in deterministic priority order.

    ``LEAGENT_TOOL_FILE_ROOTS`` is authoritative when present. The upload
    and knowledge roots are still appended so session attachments and
    indexed documents continue to resolve under narrowed deployments.
    """
    roots: list[Path] = []
    configured = _split_configured_roots(os.environ.get("LEAGENT_TOOL_FILE_ROOTS", ""))
    for item in configured:
        roots.append(_resolve_path(item))

    upload_root = _resolve_path(_default_upload_root())
    openclaw = _openclaw_root()
    if not configured:
        roots.append(upload_root)
        roots.extend(_local_profile_roots())
    else:
        roots.append(upload_root)
        if openclaw is not None:
            roots.append(openclaw)

    roots.extend(_knowledge_roots())
    return _dedupe_paths(roots)


_allowed_roots: tuple[Path, ...] | None = None


def _get_allowed_roots() -> tuple[Path, ...]:
    """Return the cached process-wide sandbox roots."""
    global _allowed_roots
    if _allowed_roots is None:
        _allowed_roots = _parse_roots()
    return _allowed_roots


def reset_roots() -> None:
    """Force re-read of roots (useful for testing)."""
    global _allowed_roots
    _allowed_roots = None


def _is_inside(resolved: Path, roots: tuple[Path, ...]) -> bool:
    """Return whether ``resolved`` is equal to or contained by any root.

    Thin wrapper kept for local call-site compatibility; delegates to
    :func:`leagent.file.primitives.is_path_inside`.
    """
    return is_path_inside(resolved, roots)


def get_project_roots(context: "ToolContext | None") -> tuple[Path, ...]:
    """Return the per-request project roots from ``context.extra``."""
    return _collect_context_dir_roots(
        context,
        "project_roots",
        tool_name="",
        request_id="",
    )


def _resolve_attachment_alias(
    raw_name: str,
    attachments: tuple[Path, ...],
    *,
    allow_create: bool,
    lookup_by_name: dict[str, str] | None = None,
) -> Path | None:
    """Resolve a user-facing filename to a concrete attached file path."""
    target = Path(raw_name).name
    if not target:
        return None

    normalized_target = _normalize_filename(target)
    if lookup_by_name and normalized_target:
        mapped = lookup_by_name.get(normalized_target)
        if mapped:
            candidate = _resolve_path(mapped)
            if allow_create or candidate.exists():
                return candidate

    for att in attachments:
        if att.is_dir():
            continue
        if not allow_create and not att.exists():
            continue

        att_name = att.name
        if (
            att_name.casefold() == target.casefold()
            or att_name.casefold().endswith(f"_{target.casefold()}")
        ):
            return att
        if normalized_target and _normalize_filename(att_name).endswith(normalized_target):
            return att
    return None


def _normalize_filename(value: str) -> str:
    compact: list[str] = []
    for ch in value.casefold():
        if ch.isalnum():
            compact.append(ch)
    return "".join(compact)


def _pick_uuid_prefixed_stored_file(session_root: Path, leaf: str) -> Path | None:
    """Resolve ``session_root / leaf`` when only ``session_root / <uuid>_leaf`` exists."""
    if not leaf or not session_root.is_dir():
        return None
    direct = session_root / leaf
    if direct.is_file():
        return direct
    matches = sorted(p for p in session_root.glob(f"*_{leaf}") if p.is_file())
    if len(matches) == 1:
        return matches[0]
    return None


def _pick_stored_file_by_leading_uuid(
    file_id: str,
    *,
    session_root: Path | None,
    attachment_roots: tuple[Path, ...],
) -> Path | None:
    """Resolve a bare document/attachment UUID to ``<uuid>_<original_name>`` on disk."""
    raw = file_id.strip()
    if not raw or not _UUID_36_RE.match(raw):
        return None

    hits: list[Path] = []
    scan_dirs: list[Path] = []
    seen: set[Path] = set()

    if session_root is not None:
        try:
            sr = _resolve_path(session_root)
            if sr.is_dir():
                scan_dirs.append(sr)
                seen.add(sr)
        except PermissionError:
            pass

    for att in attachment_roots:
        try:
            par = _resolve_path(att).parent
        except PermissionError:
            continue
        if par.is_dir() and par not in seen:
            scan_dirs.append(par)
            seen.add(par)

    for base in scan_dirs:
        try:
            hits.extend(p for p in base.glob(f"{raw}_*") if p.is_file())
        except OSError:
            continue

    uniq = sorted({h.resolve() for h in hits})
    if len(uniq) == 1:
        return uniq[0]

    uid_l = raw.lower()
    for att in attachment_roots:
        try:
            ar = _resolve_path(att)
        except PermissionError:
            continue
        if ar.is_file() and ar.name.lower().startswith(uid_l + "_"):
            hits.append(ar)
    uniq = sorted({h.resolve() for h in hits})
    if len(uniq) == 1:
        return uniq[0]

    return None


def _collect_attachment_lookup(
    context: "ToolContext | None",
) -> tuple[dict[str, str], dict[str, str]]:
    if context is None:
        return {}, {}
    raw_lookup = context.extra.get("attachment_lookup", {})
    if not isinstance(raw_lookup, dict):
        return {}, {}
    by_id_raw = raw_lookup.get("by_id", {})
    by_name_raw = raw_lookup.get("by_name", {})
    by_id = by_id_raw if isinstance(by_id_raw, dict) else {}
    by_name = by_name_raw if isinstance(by_name_raw, dict) else {}
    return (
        {str(k): str(v) for k, v in by_id.items() if isinstance(v, str)},
        {str(k): str(v) for k, v in by_name.items() if isinstance(v, str)},
    )


def _collect_attachment_roots(
    context: "ToolContext | None",
    *,
    tool_name: str,
    request_id: str,
) -> tuple[Path, ...]:
    """Extract valid absolute attachment paths from tool context."""
    if context is None:
        return ()

    raw_items = context.extra.get("attachments", ())
    roots: list[Path] = []
    for raw in raw_items:
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            candidate = _resolve_path(raw)
        except PermissionError:
            continue
        if not candidate.is_absolute():
            continue
        roots.append(candidate)
    return tuple(roots)


def _collect_context_dir_roots(
    context: "ToolContext | None",
    key: str,
    *,
    tool_name: str,
    request_id: str,
) -> tuple[Path, ...]:
    """Extract per-request directory roots from ``context.extra[key]``."""
    if context is None:
        return ()

    raw_items = context.extra.get(key, ())
    if isinstance(raw_items, (str, Path)):
        raw_items = (raw_items,)
    roots: list[Path] = []
    for raw in raw_items or ():
        if isinstance(raw, Path):
            candidate_str = str(raw)
        elif isinstance(raw, str):
            candidate_str = raw.strip()
        else:
            continue
        if not candidate_str:
            continue
        try:
            candidate = _resolve_path(candidate_str)
        except PermissionError:
            continue
        if candidate.exists() and candidate.is_dir():
            roots.append(candidate)
    return _dedupe_paths(roots)


def _session_roots(
    context: "ToolContext | None",
    global_roots: tuple[Path, ...],
) -> tuple[Path, ...]:
    """Derive likely per-session upload roots."""
    session_id = getattr(context, "session_id", None) if context is not None else None
    if not session_id:
        return ()

    roots: list[Path] = []
    try:
        from leagent.services.session.paths import get_session_path_registry

        roots.append(_resolve_path(get_session_path_registry().uploads_dir(str(session_id))))
    except Exception:  # noqa: BLE001
        roots.append(_resolve_path(Path(_default_upload_root()) / str(session_id)))

    for root in global_roots:
        roots.append(_resolve_path(root / str(session_id)))

    return _dedupe_paths(roots)


def _split_attachment_authority(
    attachments: tuple[Path, ...],
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    """Return ``(exact_files, directory_roots)`` for attachment grants."""
    files: list[Path] = []
    dirs: list[Path] = []
    for item in attachments:
        if item.exists() and item.is_dir():
            dirs.append(item)
        elif item.exists() and item.is_file():
            files.append(item)
    return _dedupe_paths(files), _dedupe_paths(dirs)


def _is_exact_file(resolved: Path, files: tuple[Path, ...]) -> bool:
    return any(resolved == item for item in files)


def _permission_error(
    raw: str,
    resolved: Path,
    *,
    allowed_roots: tuple[Path, ...],
    tool_name: str,
    request_id: str,
) -> PermissionError:
    logger.warning(
        "path_sandbox_denied",
        tool=tool_name or None,
        request_id=request_id or None,
        attempted_path=str(resolved),
        raw=raw,
        allowed_roots=[str(root) for root in allowed_roots],
    )
    return PermissionError(
        f"Path is outside the allowed sandbox: {raw!r} -> {resolved}"
    )


def _ensure_allowed(
    raw: str,
    resolved: Path,
    *,
    allowed_roots: tuple[Path, ...],
    allowed_files: tuple[Path, ...],
    tool_name: str,
    request_id: str,
) -> Path:
    if _is_inside(resolved, allowed_roots) or _is_exact_file(resolved, allowed_files):
        return resolved
    raise _permission_error(
        raw,
        resolved,
        allowed_roots=allowed_roots,
        tool_name=tool_name,
        request_id=request_id,
    )


def _existing_session_file(
    session_roots: tuple[Path, ...],
    leaf: str,
) -> Path | None:
    for root in session_roots:
        if not root.exists() or not root.is_dir():
            continue
        direct = root / leaf
        if direct.is_file():
            return _resolve_path(direct)
        picked = _pick_uuid_prefixed_stored_file(root, leaf)
        if picked is not None:
            return picked
    return None


def _system_temp_roots() -> tuple[Path, ...]:
    """Return temp directories whose generated outputs should be session-scoped."""
    roots: list[Path] = []
    for raw in (
        tempfile.gettempdir(),
        os.environ.get("TMPDIR", ""),
        os.environ.get("TEMP", ""),
        os.environ.get("TMP", ""),
        "/tmp",
    ):
        if not raw:
            continue
        try:
            root = _resolve_path(raw)
        except PermissionError:
            continue
        if root.exists() and root.is_dir():
            roots.append(root)
    return _dedupe_paths(roots)


def _ensure_session_output_root(context: "ToolContext | None") -> Path | None:
    """Create and return the current session's managed upload/output directory."""
    session_id = getattr(context, "session_id", None) if context is not None else None
    if not session_id:
        return None
    try:
        root = _resolve_path(Path(_default_upload_root()) / str(session_id))
        root.mkdir(parents=True, exist_ok=True)
        return root
    except (OSError, PermissionError):
        logger.debug("session_output_root_unavailable", exc_info=True)
        return None


def _reroute_temp_output_path(
    raw: str,
    resolved: Path,
    *,
    context: "ToolContext | None",
    allowed_roots: tuple[Path, ...],
    allowed_files: tuple[Path, ...],
    tool_name: str,
    request_id: str,
) -> Path | None:
    """Map accidental ``/tmp/name.ext`` outputs into the session workspace."""
    if not resolved.name or not _is_inside(resolved, _system_temp_roots()):
        return None

    output_root = _ensure_session_output_root(context)
    if output_root is None:
        return None

    rerouted = _resolve_path(output_root / resolved.name)
    logger.info(
        "path_sandbox_temp_output_rerouted",
        tool=tool_name or None,
        request_id=request_id or None,
        raw=raw,
        resolved=str(resolved),
        rerouted=str(rerouted),
    )
    return _ensure_allowed(
        raw,
        rerouted,
        allowed_roots=_dedupe_paths((*allowed_roots, output_root)),
        allowed_files=allowed_files,
        tool_name=tool_name,
        request_id=request_id,
    )


class PathSandbox:
    """Path resolver for file-touching tools.

    Process-wide roots come from ``LEAGENT_TOOL_FILE_ROOTS`` plus the
    upload/knowledge storage directories. Per-request roots can widen
    access for attachments, coding projects and user-authorized folders.
    """

    @staticmethod
    def resolve_safe(
        raw: str,
        *,
        context: "ToolContext | None" = None,
        allow_create: bool = False,
        tool_name: str = "",
        request_id: str = "",
    ) -> Path:
        """Resolve *raw* to an absolute, normalized path.

        Attachment aliases (``@file:``, ``@knowledge:``, bare filenames
        matching uploaded attachments) are resolved before root
        enforcement so the model can reference files by friendly name
        without bypassing the sandbox.
        """
        if not raw or not raw.strip():
            raise PermissionError("Empty path is not allowed.")

        stripped = raw.strip()
        file_ref_id: str | None = None
        if stripped.startswith("@file:"):
            ref_payload = stripped[6:].strip()
            if "#" in ref_payload:
                ref_name, ref_id = ref_payload.rsplit("#", 1)
                stripped = ref_name.strip() or ref_payload
                file_ref_id = ref_id.strip() or None
            else:
                stripped = ref_payload
        elif stripped.startswith("@knowledge:"):
            ref_payload = stripped[len("@knowledge:"):].strip()
            if "#" in ref_payload:
                ref_name, ref_id = ref_payload.rsplit("#", 1)
                stripped = ref_name.strip() or ref_payload
                tid = ref_id.strip()
                file_ref_id = tid if tid and _UUID_36_RE.match(tid) else None
            else:
                stripped = ref_payload

        global_roots = _get_allowed_roots()
        attachment_roots = _collect_attachment_roots(
            context, tool_name=tool_name, request_id=request_id,
        )
        attachment_files, attachment_dir_roots = _split_attachment_authority(attachment_roots)
        lookup_by_id, lookup_by_name = _collect_attachment_lookup(context)
        project_roots = _collect_context_dir_roots(
            context,
            "project_roots",
            tool_name=tool_name,
            request_id=request_id,
        )
        authorized_roots = _collect_context_dir_roots(
            context,
            "authorized_roots",
            tool_name=tool_name,
            request_id=request_id,
        )
        session_roots = _session_roots(context, global_roots)
        session_output_root = _ensure_session_output_root(context) if allow_create else None
        existing_session_roots = _dedupe_paths((
            *(root for root in session_roots if root.exists()),
            *((session_output_root,) if session_output_root is not None else ()),
        ))
        allowed_roots = _dedupe_paths((
            *global_roots,
            *existing_session_roots,
            *attachment_dir_roots,
            *project_roots,
            *authorized_roots,
        ))

        # --- attachment id lookup -----------------------------------------
        mapped_path = _lookup_attachment_id_path(lookup_by_id, file_ref_id)
        if not mapped_path:
            mapped_path = _lookup_attachment_id_path(lookup_by_id, stripped)
        if mapped_path:
            resolved_by_id = _resolve_path(mapped_path)
            allowed_files = _dedupe_paths((*attachment_files, resolved_by_id))
            _ensure_allowed(
                raw,
                resolved_by_id,
                allowed_roots=allowed_roots,
                allowed_files=allowed_files,
                tool_name=tool_name,
                request_id=request_id,
            )
            logger.debug(
                "path_sandbox_attachment_id_resolved",
                raw=raw,
                resolved=str(resolved_by_id),
            )
            return resolved_by_id

        # --- bare UUID file lookup ----------------------------------------
        bare_uuid_file = _pick_stored_file_by_leading_uuid(
            stripped,
            session_root=existing_session_roots[0] if existing_session_roots else None,
            attachment_roots=attachment_roots,
        )
        if bare_uuid_file is not None:
            _ensure_allowed(
                raw,
                bare_uuid_file,
                allowed_roots=allowed_roots,
                allowed_files=attachment_files,
                tool_name=tool_name,
                request_id=request_id,
            )
            logger.debug(
                "path_sandbox_bare_file_uuid_resolved",
                raw=raw,
                resolved=str(bare_uuid_file),
            )
            return bare_uuid_file

        # --- primary resolution -------------------------------------------
        is_relative = not Path(stripped).is_absolute() and not _is_user_home_path(stripped)
        resolved = _resolve_path(stripped)

        if not is_relative:
            if allow_create:
                if _is_inside(resolved, allowed_roots) or _is_exact_file(resolved, attachment_files):
                    return resolved
                rerouted = _reroute_temp_output_path(
                    raw,
                    resolved,
                    context=context,
                    allowed_roots=allowed_roots,
                    allowed_files=attachment_files,
                    tool_name=tool_name,
                    request_id=request_id,
                )
                if rerouted is not None:
                    return rerouted

            if not allow_create and not resolved.exists():
                # Absolute path that names the logical upload leaf while the
                # stored file is UUID-prefixed.
                remapped = _resolve_attachment_alias(
                    resolved.name,
                    attachment_roots,
                    allow_create=False,
                    lookup_by_name=lookup_by_name,
                )
                if remapped is not None and remapped.is_file():
                    return _ensure_allowed(
                        raw,
                        remapped,
                        allowed_roots=allowed_roots,
                        allowed_files=attachment_files,
                        tool_name=tool_name,
                        request_id=request_id,
                    )
                pick = _existing_session_file(existing_session_roots, resolved.name)
                if pick is not None:
                    return _ensure_allowed(
                        raw,
                        pick,
                        allowed_roots=allowed_roots,
                        allowed_files=attachment_files,
                        tool_name=tool_name,
                        request_id=request_id,
                    )

            return _ensure_allowed(
                raw,
                resolved,
                allowed_roots=allowed_roots,
                allowed_files=attachment_files,
                tool_name=tool_name,
                request_id=request_id,
            )

        # --- relative filename against session / upload roots -------------
        search_dirs = _dedupe_paths((
            *existing_session_roots,
            *global_roots,
            *project_roots,
            *authorized_roots,
        ))

        if allow_create:
            create_alias = _resolve_attachment_alias(
                stripped,
                attachment_roots,
                allow_create=False,
                lookup_by_name=lookup_by_name,
            )
            if create_alias is not None and not _is_inside(create_alias, existing_session_roots):
                return _ensure_allowed(
                    raw,
                    create_alias,
                    allowed_roots=allowed_roots,
                    allowed_files=attachment_files,
                    tool_name=tool_name,
                    request_id=request_id,
                )
            existing = _existing_session_file(existing_session_roots, stripped)
            if existing is not None and create_alias is None:
                return _ensure_allowed(
                    raw,
                    existing,
                    allowed_roots=allowed_roots,
                    allowed_files=attachment_files,
                    tool_name=tool_name,
                    request_id=request_id,
                )

        for base in search_dirs:
            candidate = _resolve_path(base / stripped)
            if candidate.exists():
                logger.debug(
                    "path_sandbox_relative_resolved",
                    raw=raw,
                    resolved=str(candidate),
                    base=str(base),
                )
                return _ensure_allowed(
                    raw,
                    candidate,
                    allowed_roots=allowed_roots,
                    allowed_files=attachment_files,
                    tool_name=tool_name,
                    request_id=request_id,
                )
            if allow_create and _is_inside(candidate, allowed_roots):
                # Output paths must name the file to create, not an existing
                # attachment alias with the same display name.
                return candidate

        if not allow_create:
            alias_match = _resolve_attachment_alias(
                stripped,
                attachment_roots,
                allow_create=False,
                lookup_by_name=lookup_by_name,
            )
            if alias_match is not None:
                logger.debug(
                    "path_sandbox_attachment_alias_resolved",
                    raw=raw,
                    resolved=str(alias_match),
                )
                return _ensure_allowed(
                    raw,
                    alias_match,
                    allowed_roots=allowed_roots,
                    allowed_files=attachment_files,
                    tool_name=tool_name,
                    request_id=request_id,
                )

        if allow_create:
            candidate = _resolve_path(stripped)
            return _ensure_allowed(
                raw,
                candidate,
                allowed_roots=allowed_roots,
                allowed_files=attachment_files,
                tool_name=tool_name,
                request_id=request_id,
            )

        raise _permission_error(
            raw,
            resolved,
            allowed_roots=allowed_roots,
            tool_name=tool_name,
            request_id=request_id,
        )

    @staticmethod
    def is_safe(
        raw: str,
        *,
        context: "ToolContext | None" = None,
        allow_create: bool = False,
    ) -> bool:
        """Non-raising path check."""
        try:
            PathSandbox.resolve_safe(
                raw, context=context, allow_create=allow_create,
            )
            return True
        except (PermissionError, ValueError, OSError):
            return False
