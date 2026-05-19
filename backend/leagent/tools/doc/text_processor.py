"""Text File Processor Tool — encoding-aware read, analysis, search, and diff.

Supports many legacy and locale-specific encodings, BOM detection, optional
charset-normalizer integration, strict/replace/ignore decode modes,
inspection helpers for ambiguous files, and UTF-8 (or explicit codec) write
of string ``data`` to sandboxed paths.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any, Final

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

try:
    from charset_normalizer import from_bytes as _cn_from_bytes

    _HAS_CHARSET_NORMALIZER = True
except ImportError:
    _cn_from_bytes = None
    _HAS_CHARSET_NORMALIZER = False

# Order matters: earlier = preferred when multiple strict decodings succeed (e.g. ASCII).
_ORDERED_TEXT_ENCODINGS: Final[tuple[str, ...]] = (
    "utf-8",
    "utf-8-sig",
    "gb18030",
    "gbk",
    "big5",
    "utf-16-le",
    "utf-16-be",
    "utf-16",
    "shift_jis",
    "euc-jp",
    "euc-kr",
    "cp949",
    "cp932",
    "cp936",
    "cp1252",
    "cp1251",
    "mac_roman",
    "koi8-r",
)

_MAX_DETECT_BYTES: Final[int] = 524_288
_DEFAULT_DETECT_BYTES: Final[int] = 65_536
_BINARY_NUL_RATIO: Final[float] = 0.12
_PREVIEW_LEN: Final[int] = 400


def _normalize_codec_name(name: str) -> str:
    n = name.strip().lower().replace("_", "-")
    aliases = {"utf8": "utf-8", "ascii": "ascii"}
    return aliases.get(n, n)


def _sniff_bom(raw: bytes) -> tuple[str | None, int]:
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", 3
    if raw.startswith(b"\xff\xfe\x00\x00"):
        return "utf-32-le", 4
    if raw.startswith(b"\x00\x00\xfe\xff"):
        return "utf-32-be", 4
    if raw.startswith(b"\xff\xfe"):
        return "utf-16-le", 2
    if raw.startswith(b"\xfe\xff"):
        return "utf-16-be", 2
    return None, 0


def _nul_ratio(raw: bytes) -> float:
    if not raw:
        return 0.0
    return raw.count(0) / len(raw)


def _likely_utf16_le_no_bom(raw: bytes) -> bool:
    """Heuristic: many NULs at odd indices suggests UTF-16-LE text."""
    if len(raw) < 8:
        return False
    if len(raw) % 2 != 0:
        raw = raw[:-1]
    odd_nul = sum(1 for i in range(1, min(len(raw), 4096), 2) if raw[i] == 0)
    even_nul = sum(1 for i in range(0, min(len(raw), 4096), 2) if raw[i] == 0)
    sample_pairs = min(len(raw), 4096) // 2
    if sample_pairs == 0:
        return False
    return odd_nul / sample_pairs > 0.25 and even_nul / sample_pairs < 0.05


def _likely_utf16_be_no_bom(raw: bytes) -> bool:
    if len(raw) < 8:
        return False
    if len(raw) % 2 != 0:
        raw = raw[:-1]
    even_nul = sum(1 for i in range(0, min(len(raw), 4096), 2) if raw[i] == 0)
    odd_nul = sum(1 for i in range(1, min(len(raw), 4096), 2) if raw[i] == 0)
    sample_pairs = min(len(raw), 4096) // 2
    if sample_pairs == 0:
        return False
    return even_nul / sample_pairs > 0.25 and odd_nul / sample_pairs < 0.05


def _line_ending_breakdown(text: str) -> dict[str, Any]:
    crlf = text.count("\r\n")
    rest = text.replace("\r\n", "\n")
    lf = rest.count("\n")
    cr = rest.count("\r")
    if crlf >= lf and crlf >= cr and crlf > 0:
        dominant = "crlf"
    elif cr > lf and cr > 0:
        dominant = "cr"
    else:
        dominant = "lf"
    return {
        "crlf": crlf,
        "lf": lf,
        "cr_lone": cr,
        "dominant": dominant,
    }


def _strict_decode_candidates(raw: bytes) -> list[dict[str, Any]]:
    """Encodings that strict-decode the sample.

    Latin-1 / ISO-8859-1 are excluded from the main pass (they accept every byte
    sequence and would mask binary garbage); they are appended only as a last
    resort so ``detect_encoding`` can still surface a low-confidence guess.
    """
    ok: list[dict[str, Any]] = []
    for enc in _ORDERED_TEXT_ENCODINGS:
        try:
            text = raw.decode(enc, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
        ok.append({
            "encoding": enc,
            "decoded_chars": len(text),
            "replacement_free": True,
        })
    if not ok:
        text = raw.decode("latin-1", errors="strict")
        ok.append({
            "encoding": "latin-1",
            "decoded_chars": len(text),
            "replacement_free": True,
            "fallback_only": True,
        })
    return ok


def _charset_normalizer_guess(raw: bytes) -> dict[str, Any] | None:
    if not _HAS_CHARSET_NORMALIZER or _cn_from_bytes is None:
        return None
    try:
        matches = _cn_from_bytes(raw)
    except Exception:
        return None
    if not matches:
        return None
    best = matches.best()
    if best is None:
        return None
    enc = _normalize_codec_name(str(best.encoding))
    try:
        raw.decode(enc, errors="strict")
    except (UnicodeDecodeError, LookupError):
        return None
    chaos = getattr(best, "chaos", None)
    return {
        "encoding": enc,
        "chaos": float(chaos) if chaos is not None else None,
        "language": getattr(best, "language", None),
    }


def analyze_bytes(raw: bytes) -> dict[str, Any]:
    """Core detection logic used by detect_encoding and auto-read paths."""
    if not raw:
        return {
            "encoding": "utf-8",
            "confidence": "high",
            "source": "empty",
            "bom_encoding": None,
            "bom_length": 0,
            "likely_binary": False,
            "nul_ratio": 0.0,
            "charset_normalizer": None,
            "strict_candidates": [{"encoding": "utf-8", "decoded_chars": 0, "replacement_free": True}],
        }

    bom_enc, bom_len = _sniff_bom(raw)
    nul_r = _nul_ratio(raw)
    likely_binary = nul_r >= _BINARY_NUL_RATIO and bom_enc is None

    cn = _charset_normalizer_guess(raw)

    strict_list = _strict_decode_candidates(raw)
    primary: str | None = None
    source = "heuristic"

    if bom_enc:
        primary = bom_enc
        source = "bom"
    elif cn and cn["encoding"]:
        primary = cn["encoding"]
        source = "charset_normalizer"
    elif strict_list:
        primary = strict_list[0]["encoding"]
        if _likely_utf16_le_no_bom(raw) and any(x["encoding"] == "utf-16-le" for x in strict_list):
            primary = "utf-16-le"
        elif _likely_utf16_be_no_bom(raw) and any(x["encoding"] == "utf-16-be" for x in strict_list):
            primary = "utf-16-be"
        source = "heuristic"

    only_latin_fallback = len(strict_list) == 1 and strict_list[0].get("fallback_only")
    if likely_binary and only_latin_fallback:
        primary = None
        source = "binary_heuristic"

    conf = "high"
    if primary is None:
        conf = "low"
    elif source == "charset_normalizer" and cn:
        chaos = cn.get("chaos")
        if chaos is not None:
            if chaos >= 0.15:
                conf = "low"
            elif chaos >= 0.03:
                conf = "medium"
    elif strict_list and strict_list[0].get("fallback_only"):
        conf = "low"

    return {
        "encoding": primary or "utf-8",
        "confidence": conf,
        "source": source,
        "bom_encoding": bom_enc,
        "bom_length": bom_len,
        "likely_binary": bool(likely_binary and only_latin_fallback),
        "nul_ratio": round(nul_r, 6),
        "charset_normalizer": cn,
        "strict_candidates": strict_list[:12],
    }


def _compile_pattern(pattern: str, flags_str: str | None) -> re.Pattern[str]:
    flags = 0
    for c in flags_str or "":
        if c in "iI":
            flags |= re.IGNORECASE
        elif c in "mM":
            flags |= re.MULTILINE
        elif c in "sS":
            flags |= re.DOTALL
        elif c in "xX":
            flags |= re.VERBOSE
    return re.compile(pattern, flags)


class TextFileProcessorTool(SyncTool):
    """Decode, analyse, and write text files under the path sandbox."""

    name = "text_processor"
    description = (
        "Professional text-file processor: auto-detect BOM and encodings (UTF-8 family, "
        "UTF-16/32, GB18030/GBK/Big5, Japanese/Korean legacy, Windows code pages, Latin-1), "
        "optional charset-normalizer when installed, decode with strict/replace/ignore, "
        "regex search with flags, stats, head/tail, unified diff, detect_encoding, "
        "try_decodings, and write (string data to file_path, default UTF-8). "
        "Only user-attached or sandboxed paths."
    )
    category = ToolCategory.DOC
    version = "1.2.0"
    timeout_sec = 120
    aliases = ["text", "txt", "text_reader"]
    search_hint = (
        "text file encoding utf-8 gb18030 utf-16 bom detect decode read write search "
        "regex stats head tail diff charset"
    )
    is_concurrency_safe = True
    is_read_only = False
    is_destructive = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    # file_path: allow_create (read + write + create new under session), like csv_processor.
    path_params = ("file_path_2",)
    output_path_params = ("file_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "read",
                        "write",
                        "search",
                        "stats",
                        "head",
                        "tail",
                        "diff",
                        "detect_encoding",
                        "try_decodings",
                    ],
                    "description": "Text operation: read/write/search/stats/head/tail/diff, or encoding diagnostics.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to the text file.",
                },
                "file_path_2": {
                    "type": "string",
                    "description": "Second file path for diff operation.",
                },
                "encoding": {
                    "type": "string",
                    "description": "File encoding (codec name). If omitted, auto-detect for read/search/stats/head/tail.",
                },
                "encoding_2": {
                    "type": "string",
                    "description": "Encoding for file_path_2 in diff when it differs from encoding.",
                },
                "errors": {
                    "type": "string",
                    "enum": ["strict", "replace", "ignore"],
                    "description": "Unicode error handler when decoding. Default replace.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern for search operation.",
                },
                "regex_flags": {
                    "type": "string",
                    "description": "Regex flag letters: i=ignorecase, m=multiline, s=dotall, x=verbose.",
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of lines for head/tail. Default 20.",
                    "minimum": 1,
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Context lines around search matches. Default 2.",
                    "minimum": 0,
                },
                "max_matches": {
                    "type": "integer",
                    "description": "Maximum search matches to return. Default 100.",
                    "minimum": 1,
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Max characters returned for read (default 500000).",
                    "minimum": 1,
                    "maximum": 500_000,
                },
                "sample_bytes": {
                    "type": "integer",
                    "description": "Bytes to read from file start for detect_encoding / try_decodings (256–524288).",
                    "minimum": 256,
                    "maximum": _MAX_DETECT_BYTES,
                },
                "encodings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Codec names to try for try_decodings (required for that operation).",
                },
                "data": {
                    "type": "string",
                    "description": "Full text content for write operation (UTF-8 by default; set encoding).",
                },
                "max_write_chars": {
                    "type": "integer",
                    "description": "Max characters accepted for write (default 500000, max 500000).",
                    "minimum": 1,
                    "maximum": 500_000,
                },
            },
            "required": ["operation", "file_path"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "read")
        return f"Processing text file ({op})"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        operation = params["operation"]
        file_path = Path(params["file_path"]).expanduser().resolve()

        dispatch: dict[str, Any] = {
            "read": self._read,
            "write": self._write,
            "search": self._search,
            "stats": self._stats,
            "head": self._head,
            "tail": self._tail,
            "diff": self._diff,
            "detect_encoding": self._detect_encoding_op,
            "try_decodings": self._try_decodings,
        }
        if operation not in dispatch:
            raise ValueError(f"Unknown operation: {operation}")

        return dispatch[operation](file_path, params)

    def _read_raw_sample(self, file_path: Path, n: int) -> bytes:
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        with file_path.open("rb") as f:
            return f.read(n)

    def _resolve_encoding(self, file_path: Path, encoding: str | None) -> str:
        if encoding:
            return encoding.strip()
        raw = self._read_raw_sample(file_path, min(_DEFAULT_DETECT_BYTES, max(file_path.stat().st_size, 1)))
        analysis = analyze_bytes(raw)
        if analysis.get("likely_binary") and not analysis.get("strict_candidates"):
            return "utf-8"
        return analysis["encoding"]

    def _read_text(
        self,
        file_path: Path,
        encoding: str | None,
        errors: str,
    ) -> tuple[str, str, dict[str, Any]]:
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        enc = self._resolve_encoding(file_path, encoding)
        # newline="" preserves actual CR/LF bytes in the str (no universal newline translation).
        with file_path.open("r", encoding=enc, errors=errors, newline="") as f:
            text = f.read()
        meta = {"used_encoding": enc, "errors": errors}
        if not encoding:
            sample = self._read_raw_sample(file_path, min(_DEFAULT_DETECT_BYTES, file_path.stat().st_size or 1))
            meta["detection"] = analyze_bytes(sample)
        return text, enc, meta

    def _read(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        err = params.get("errors") or "replace"
        text, enc, meta = self._read_text(file_path, params.get("encoding"), err)
        max_chars = min(int(params.get("max_chars") or 500_000), 500_000)
        truncated = len(text) > max_chars
        le = _line_ending_breakdown(text)
        out: dict[str, Any] = {
            "text": text[:max_chars],
            "encoding": enc,
            "size": file_path.stat().st_size,
            "truncated": truncated,
            "line_endings": le,
            "decode": meta,
        }
        if err == "replace":
            out["replacement_char_count"] = text.count("\ufffd")
        return out

    def _write(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        raw = params.get("data")
        if raw is None:
            raise ValueError("'data' is required for write operation")
        if not isinstance(raw, str):
            raise TypeError("'data' must be a string")

        max_w = min(int(params.get("max_write_chars") or 500_000), 500_000)
        if len(raw) > max_w:
            raise ValueError(f"'data' exceeds maximum length ({max_w} characters)")

        enc = (params.get("encoding") or "utf-8").strip()
        write_errors = params.get("errors") or "strict"
        if write_errors not in ("strict", "replace", "ignore"):
            write_errors = "strict"

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding=enc, errors=write_errors, newline="") as f:
            f.write(raw)

        sz = file_path.stat().st_size
        return {
            "success": True,
            "file_path": str(file_path),
            "encoding": enc,
            "chars_written": len(raw),
            "size_bytes": sz,
        }

    def _search(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        pattern = params.get("pattern")
        if not pattern:
            raise ValueError("'pattern' is required for search operation")

        err = params.get("errors") or "replace"
        text, enc, _ = self._read_text(file_path, params.get("encoding"), err)
        lines = text.splitlines()
        ctx = params.get("context_lines", 2)
        max_matches = params.get("max_matches", 100)

        compiled = _compile_pattern(pattern, params.get("regex_flags"))
        matches: list[dict[str, Any]] = []

        for i, line in enumerate(lines):
            if compiled.search(line):
                start = max(0, i - ctx)
                end = min(len(lines), i + ctx + 1)
                matches.append({
                    "line_number": i + 1,
                    "line": line,
                    "context": lines[start:end],
                })
                if len(matches) >= max_matches:
                    break

        return {
            "file": str(file_path),
            "pattern": pattern,
            "encoding": enc,
            "matches": matches,
            "match_count": len(matches),
            "total_lines": len(lines),
        }

    def _stats(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        err = params.get("errors") or "replace"
        text, enc, meta = self._read_text(file_path, params.get("encoding"), err)
        lines = text.splitlines()
        words = text.split()
        non_empty = sum(1 for ln in lines if ln.strip())

        return {
            "file": str(file_path),
            "encoding": enc,
            "decode": meta,
            "size_bytes": file_path.stat().st_size,
            "line_count": len(lines),
            "non_empty_lines": non_empty,
            "word_count": len(words),
            "char_count": len(text),
            "avg_line_length": round(len(text) / max(len(lines), 1), 1),
            "line_endings": _line_ending_breakdown(text),
            "replacement_char_count": text.count("\ufffd") if err == "replace" else 0,
        }

    def _head(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        err = params.get("errors") or "replace"
        text, enc, _ = self._read_text(file_path, params.get("encoding"), err)
        n = params.get("lines", 20)
        lines = text.splitlines()
        return {
            "file": str(file_path),
            "encoding": enc,
            "lines": lines[:n],
            "shown": min(n, len(lines)),
            "total_lines": len(lines),
        }

    def _tail(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        err = params.get("errors") or "replace"
        text, enc, _ = self._read_text(file_path, params.get("encoding"), err)
        n = params.get("lines", 20)
        lines = text.splitlines()
        return {
            "file": str(file_path),
            "encoding": enc,
            "lines": lines[-n:],
            "shown": min(n, len(lines)),
            "total_lines": len(lines),
        }

    def _diff(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        file_path_2 = params.get("file_path_2")
        if not file_path_2:
            raise ValueError("'file_path_2' is required for diff operation")

        path2 = Path(file_path_2).expanduser().resolve()
        err = params.get("errors") or "replace"
        enc1 = params.get("encoding")
        enc2 = params.get("encoding_2") or enc1

        text1, _, _ = self._read_text(file_path, enc1, err)
        text2, _, _ = self._read_text(path2, enc2, err)

        lines1 = text1.splitlines(keepends=True)
        lines2 = text2.splitlines(keepends=True)

        diff_lines = list(difflib.unified_diff(
            lines1, lines2,
            fromfile=str(file_path),
            tofile=str(path2),
            lineterm="",
        ))

        additions = sum(1 for ln in diff_lines if ln.startswith("+") and not ln.startswith("+++"))
        deletions = sum(1 for ln in diff_lines if ln.startswith("-") and not ln.startswith("---"))

        return {
            "file_1": str(file_path),
            "file_2": str(path2),
            "encoding_1": enc1 or "auto",
            "encoding_2": enc2 or "auto",
            "diff": "\n".join(diff_lines[:5000]),
            "additions": additions,
            "deletions": deletions,
            "identical": len(diff_lines) == 0,
        }

    def _detect_encoding_op(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        n = int(params.get("sample_bytes") or _DEFAULT_DETECT_BYTES)
        n = max(256, min(n, _MAX_DETECT_BYTES))
        raw = self._read_raw_sample(file_path, n)
        analysis = analyze_bytes(raw)
        return {
            "file": str(file_path),
            "sample_bytes": len(raw),
            "file_size": file_path.stat().st_size,
            "encoding": analysis["encoding"],
            "confidence": analysis["confidence"],
            "source": analysis["source"],
            "bom_encoding": analysis["bom_encoding"],
            "bom_length": analysis["bom_length"],
            "likely_binary": analysis["likely_binary"],
            "nul_ratio": analysis["nul_ratio"],
            "charset_normalizer": analysis["charset_normalizer"],
            "strict_decode_candidates": analysis["strict_candidates"],
            "charset_normalizer_available": _HAS_CHARSET_NORMALIZER,
        }

    def _try_decodings(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        encs = params.get("encodings")
        if not encs or not isinstance(encs, list):
            raise ValueError("'encodings' (non-empty list) is required for try_decodings")

        n = int(params.get("sample_bytes") or _DEFAULT_DETECT_BYTES)
        n = max(256, min(n, _MAX_DETECT_BYTES))
        raw = self._read_raw_sample(file_path, n)

        results: list[dict[str, Any]] = []
        for enc_raw in encs:
            enc = str(enc_raw).strip()
            row: dict[str, Any] = {"encoding": enc, "strict_ok": False, "replace_preview": None, "error": None}
            try:
                decoded = raw.decode(enc, errors="strict")
                row["strict_ok"] = True
                row["decoded_chars"] = len(decoded)
                row["preview"] = decoded[:_PREVIEW_LEN] + ("…" if len(decoded) > _PREVIEW_LEN else "")
                row["line_endings"] = _line_ending_breakdown(decoded)
            except (UnicodeDecodeError, LookupError) as e:
                row["error"] = str(e)
                try:
                    dec_rep = raw.decode(enc, errors="replace")
                    row["replace_preview"] = dec_rep[:_PREVIEW_LEN] + ("…" if len(dec_rep) > _PREVIEW_LEN else "")
                    row["replacement_char_count"] = dec_rep.count("\ufffd")
                except LookupError as e2:
                    row["replace_error"] = str(e2)
            results.append(row)

        return {
            "file": str(file_path),
            "sample_bytes": len(raw),
            "results": results,
        }
