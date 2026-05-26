"""Text File Processor Tool — professional text manipulation, encoding, and authoring.

Full-featured text processing toolkit:
- Encoding-aware read with BOM detection, charset-normalizer integration
- Write/create text files with any encoding
- Search with regex, context lines, capture groups
- Replace: find-and-replace with regex support (single/all occurrences)
- Insert: add text at specific line numbers
- Transform: case conversion, trimming, wrapping, indentation, sorting
- Extract: pull out lines matching patterns, line ranges, or between markers
- Split: break file into parts by delimiter or line count
- Join: concatenate multiple files
- Stats: word count, line count, character frequency, encoding info
- Head/tail, diff, detect_encoding, try_decodings
"""

from __future__ import annotations

import difflib
import re
import textwrap
from pathlib import Path
from typing import Any, Final

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

try:
    from charset_normalizer import from_bytes as _cn_from_bytes

    _HAS_CHARSET_NORMALIZER = True
except ImportError:
    _cn_from_bytes = None
    _HAS_CHARSET_NORMALIZER = False

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
    """Professional text-file processor with full manipulation capabilities."""

    name = "text_processor"
    description = (
        "Professional text-file processor: read/write with encoding auto-detection "
        "(UTF-8, UTF-16/32, GB18030/GBK/Big5, Japanese/Korean, Windows code pages), "
        "regex search with capture groups, find-and-replace (single/all/regex), "
        "insert lines at position, append/prepend content, "
        "text transforms (uppercase/lowercase/title/strip/wrap/indent/dedent/sort/reverse/unique/number_lines), "
        "extract by pattern/line-range/markers, split file by delimiter or lines, "
        "join/concatenate multiple files, stats, head/tail, unified diff, "
        "detect_encoding, try_decodings. "
        "Use this tool for any text file manipulation without writing code."
    )
    category = ToolCategory.DOC
    version = "2.0.0"
    timeout_sec = 120
    aliases = ["text", "txt", "text_writer", "text_reader"]
    search_hint = (
        "text file encoding utf-8 gb18030 utf-16 bom detect decode read write search "
        "regex replace insert append transform extract split join stats head tail diff "
        "charset uppercase lowercase wrap indent sort unique"
    )
    is_concurrency_safe = True
    is_read_only = False
    is_destructive = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    path_params = ("file_path_2", "source_files")
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
                        "replace",
                        "insert",
                        "append",
                        "prepend",
                        "transform",
                        "extract",
                        "split",
                        "join",
                        "stats",
                        "head",
                        "tail",
                        "diff",
                        "detect_encoding",
                        "try_decodings",
                    ],
                    "description": (
                        "Operation: read|write|search|replace|insert|append|prepend|"
                        "transform|extract|split|join|stats|head|tail|diff|detect_encoding|try_decodings"
                    ),
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
                    "description": "File encoding (codec name). If omitted, auto-detect.",
                },
                "encoding_2": {
                    "type": "string",
                    "description": "Encoding for file_path_2 in diff.",
                },
                "errors": {
                    "type": "string",
                    "enum": ["strict", "replace", "ignore"],
                    "description": "Unicode error handler. Default: replace.",
                },
                "data": {
                    "type": "string",
                    "description": "Text content for write/append/prepend/insert operations.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern for search/replace/extract operations.",
                },
                "replacement": {
                    "type": "string",
                    "description": "Replacement string for replace operation. Supports \\1, \\2 backreferences.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences (true) or only first (false). Default: true.",
                },
                "regex_flags": {
                    "type": "string",
                    "description": "Regex flag letters: i=ignorecase, m=multiline, s=dotall, x=verbose.",
                },
                "line_number": {
                    "type": "integer",
                    "description": "Line number for insert operation (1-indexed). 0 or negative = from end.",
                    "minimum": 0,
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
                "transform_type": {
                    "type": "string",
                    "enum": [
                        "uppercase",
                        "lowercase",
                        "title_case",
                        "capitalize",
                        "strip",
                        "lstrip",
                        "rstrip",
                        "wrap",
                        "indent",
                        "dedent",
                        "sort_lines",
                        "reverse_lines",
                        "unique_lines",
                        "number_lines",
                        "remove_blank_lines",
                        "collapse_blank_lines",
                        "normalize_whitespace",
                        "tabs_to_spaces",
                        "spaces_to_tabs",
                    ],
                    "description": "Type of text transformation for transform operation.",
                },
                "width": {
                    "type": "integer",
                    "description": "Line width for wrap transform (default: 80).",
                    "minimum": 20,
                    "maximum": 200,
                },
                "indent_str": {
                    "type": "string",
                    "description": "Indentation string for indent transform (default: '    ').",
                },
                "tab_size": {
                    "type": "integer",
                    "description": "Tab size for tabs_to_spaces/spaces_to_tabs (default: 4).",
                    "minimum": 1,
                    "maximum": 8,
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line (1-indexed) for extract by line range.",
                    "minimum": 1,
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line (inclusive, 1-indexed) for extract by line range.",
                    "minimum": 1,
                },
                "start_marker": {
                    "type": "string",
                    "description": "Start marker (regex) for extract between markers.",
                },
                "end_marker": {
                    "type": "string",
                    "description": "End marker (regex) for extract between markers.",
                },
                "delimiter": {
                    "type": "string",
                    "description": "Delimiter for split operation (regex). Default: page break or '---'.",
                },
                "chunk_lines": {
                    "type": "integer",
                    "description": "Lines per chunk for split by line count.",
                    "minimum": 1,
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for split operation.",
                },
                "source_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file paths to join/concatenate.",
                },
                "separator": {
                    "type": "string",
                    "description": "Separator between joined files (default: '\\n').",
                },
                "sample_bytes": {
                    "type": "integer",
                    "description": "Bytes for detect_encoding/try_decodings (256–524288).",
                    "minimum": 256,
                    "maximum": _MAX_DETECT_BYTES,
                },
                "encodings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Codec names to try for try_decodings.",
                },
                "max_write_chars": {
                    "type": "integer",
                    "description": "Max characters for write (default 500000).",
                    "minimum": 1,
                    "maximum": 500_000,
                },
                "sort_reverse": {
                    "type": "boolean",
                    "description": "Reverse sort order for sort_lines. Default false.",
                },
                "sort_key": {
                    "type": "string",
                    "enum": ["alpha", "numeric", "length"],
                    "description": "Sort key for sort_lines. Default: alpha.",
                },
            },
            "required": ["operation", "file_path"],
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "read")
        return f"Text processing: {op}"

    def recover_raw_args(self, raw: str) -> dict[str, Any] | None:
        from leagent.tools.doc._recovery import recover_doc_tool_args

        return recover_doc_tool_args(raw, content_key="data")

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        params = self._normalize_params(params)
        operation = params["operation"]
        file_path = Path(params["file_path"]).expanduser().resolve()

        dispatch: dict[str, Any] = {
            "read": self._read,
            "write": self._write,
            "search": self._search,
            "replace": self._replace,
            "insert": self._insert,
            "append": self._append,
            "prepend": self._prepend,
            "transform": self._transform,
            "extract": self._extract,
            "split": self._split,
            "join": self._join,
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

    @staticmethod
    def _normalize_params(params: dict[str, Any]) -> dict[str, Any]:
        """Normalize LLM-generated parameter variations to canonical names."""
        p = dict(params)
        # Accept content/text/body as aliases for data
        if "data" not in p or p["data"] is None:
            for alias in ("content", "text", "body", "markdown"):
                if alias in p and p[alias] is not None:
                    p["data"] = p[alias]
                    break
        return p

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
        with file_path.open("r", encoding=enc, errors=errors, newline="") as f:
            text = f.read()
        meta = {"used_encoding": enc, "errors": errors}
        if not encoding:
            sample = self._read_raw_sample(file_path, min(_DEFAULT_DETECT_BYTES, file_path.stat().st_size or 1))
            meta["detection"] = analyze_bytes(sample)
        return text, enc, meta

    def _write_file(self, file_path: Path, content: str, encoding: str, errors: str) -> dict[str, Any]:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding=encoding, errors=errors, newline="") as f:
            f.write(content)
        sz = file_path.stat().st_size
        return {
            "success": True,
            "file_path": str(file_path),
            "encoding": encoding,
            "chars_written": len(content),
            "size_bytes": sz,
        }

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

        return self._write_file(file_path, raw, enc, write_errors)

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
            m = compiled.search(line)
            if m:
                start = max(0, i - ctx)
                end = min(len(lines), i + ctx + 1)
                match_info: dict[str, Any] = {
                    "line_number": i + 1,
                    "line": line,
                    "context": lines[start:end],
                    "match": m.group(0),
                }
                if m.groups():
                    match_info["groups"] = list(m.groups())
                matches.append(match_info)
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

    def _replace(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        pattern = params.get("pattern")
        replacement = params.get("replacement")
        if not pattern:
            raise ValueError("'pattern' is required for replace operation")
        if replacement is None:
            raise ValueError("'replacement' is required for replace operation")

        err = params.get("errors") or "replace"
        text, enc, _ = self._read_text(file_path, params.get("encoding"), err)
        compiled = _compile_pattern(pattern, params.get("regex_flags"))
        replace_all = params.get("replace_all", True)

        if replace_all:
            new_text, count = compiled.subn(replacement, text)
        else:
            new_text, count = compiled.subn(replacement, text, count=1)

        write_errors = params.get("errors") or "strict"
        if write_errors not in ("strict", "replace", "ignore"):
            write_errors = "strict"

        self._write_file(file_path, new_text, enc, write_errors)
        return {
            "success": True,
            "file_path": str(file_path),
            "pattern": pattern,
            "replacement": replacement,
            "replacements_made": count,
            "replace_all": replace_all,
        }

    def _insert(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        data = params.get("data")
        if data is None:
            raise ValueError("'data' is required for insert operation")

        line_number = params.get("line_number", 1)
        err = params.get("errors") or "replace"

        if file_path.exists():
            text, enc, _ = self._read_text(file_path, params.get("encoding"), err)
            lines = text.splitlines(keepends=True)
        else:
            lines = []
            enc = (params.get("encoding") or "utf-8").strip()

        insert_lines = data.splitlines(keepends=True)
        if insert_lines and not insert_lines[-1].endswith("\n"):
            insert_lines[-1] += "\n"

        if line_number <= 0:
            idx = max(0, len(lines) + line_number)
        else:
            idx = min(line_number - 1, len(lines))

        new_lines = lines[:idx] + insert_lines + lines[idx:]
        new_text = "".join(new_lines)

        write_errors = params.get("errors") or "strict"
        if write_errors not in ("strict", "replace", "ignore"):
            write_errors = "strict"

        self._write_file(file_path, new_text, enc, write_errors)
        return {
            "success": True,
            "file_path": str(file_path),
            "inserted_at_line": idx + 1,
            "lines_inserted": len(insert_lines),
            "total_lines": len(new_lines),
        }

    def _append(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        data = params.get("data")
        if data is None:
            raise ValueError("'data' is required for append operation")

        enc = (params.get("encoding") or "utf-8").strip()
        err = params.get("errors") or "replace"

        existing = ""
        if file_path.exists():
            existing, enc, _ = self._read_text(file_path, params.get("encoding"), err)

        separator = "\n" if existing and not existing.endswith("\n") else ""
        new_content = existing + separator + data

        write_errors = params.get("errors") or "strict"
        if write_errors not in ("strict", "replace", "ignore"):
            write_errors = "strict"

        self._write_file(file_path, new_content, enc, write_errors)
        return {
            "success": True,
            "file_path": str(file_path),
            "appended_chars": len(data),
            "total_chars": len(new_content),
        }

    def _prepend(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        data = params.get("data")
        if data is None:
            raise ValueError("'data' is required for prepend operation")

        enc = (params.get("encoding") or "utf-8").strip()
        err = params.get("errors") or "replace"

        existing = ""
        if file_path.exists():
            existing, enc, _ = self._read_text(file_path, params.get("encoding"), err)

        separator = "\n" if data and not data.endswith("\n") else ""
        new_content = data + separator + existing

        write_errors = params.get("errors") or "strict"
        if write_errors not in ("strict", "replace", "ignore"):
            write_errors = "strict"

        self._write_file(file_path, new_content, enc, write_errors)
        return {
            "success": True,
            "file_path": str(file_path),
            "prepended_chars": len(data),
            "total_chars": len(new_content),
        }

    def _transform(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        transform_type = params.get("transform_type")
        if not transform_type:
            raise ValueError("'transform_type' is required for transform operation")

        err = params.get("errors") or "replace"
        text, enc, _ = self._read_text(file_path, params.get("encoding"), err)

        if transform_type == "uppercase":
            result = text.upper()
        elif transform_type == "lowercase":
            result = text.lower()
        elif transform_type == "title_case":
            result = text.title()
        elif transform_type == "capitalize":
            lines = text.splitlines(keepends=True)
            result = "".join(line.capitalize() for line in lines)
        elif transform_type == "strip":
            lines = text.splitlines()
            result = "\n".join(line.strip() for line in lines) + "\n"
        elif transform_type == "lstrip":
            lines = text.splitlines()
            result = "\n".join(line.lstrip() for line in lines) + "\n"
        elif transform_type == "rstrip":
            lines = text.splitlines()
            result = "\n".join(line.rstrip() for line in lines) + "\n"
        elif transform_type == "wrap":
            width = params.get("width", 80)
            lines = text.splitlines()
            wrapped: list[str] = []
            for line in lines:
                if line.strip():
                    wrapped.extend(textwrap.wrap(line, width=width))
                else:
                    wrapped.append("")
            result = "\n".join(wrapped) + "\n"
        elif transform_type == "indent":
            indent_str = params.get("indent_str", "    ")
            result = textwrap.indent(text, indent_str)
        elif transform_type == "dedent":
            result = textwrap.dedent(text)
        elif transform_type == "sort_lines":
            lines = text.splitlines()
            reverse = params.get("sort_reverse", False)
            sort_key = params.get("sort_key", "alpha")
            if sort_key == "numeric":
                def num_key(s: str) -> float:
                    nums = re.findall(r"-?\d+\.?\d*", s)
                    return float(nums[0]) if nums else float("inf")
                lines.sort(key=num_key, reverse=reverse)
            elif sort_key == "length":
                lines.sort(key=len, reverse=reverse)
            else:
                lines.sort(key=str.lower, reverse=reverse)
            result = "\n".join(lines) + "\n"
        elif transform_type == "reverse_lines":
            lines = text.splitlines()
            lines.reverse()
            result = "\n".join(lines) + "\n"
        elif transform_type == "unique_lines":
            lines = text.splitlines()
            seen: set[str] = set()
            unique: list[str] = []
            for line in lines:
                if line not in seen:
                    seen.add(line)
                    unique.append(line)
            result = "\n".join(unique) + "\n"
        elif transform_type == "number_lines":
            lines = text.splitlines()
            width = len(str(len(lines)))
            result = "\n".join(f"{i+1:>{width}} | {line}" for i, line in enumerate(lines)) + "\n"
        elif transform_type == "remove_blank_lines":
            lines = text.splitlines()
            result = "\n".join(line for line in lines if line.strip()) + "\n"
        elif transform_type == "collapse_blank_lines":
            result = re.sub(r"\n{3,}", "\n\n", text)
        elif transform_type == "normalize_whitespace":
            lines = text.splitlines()
            result = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in lines) + "\n"
        elif transform_type == "tabs_to_spaces":
            tab_size = params.get("tab_size", 4)
            result = text.replace("\t", " " * tab_size)
        elif transform_type == "spaces_to_tabs":
            tab_size = params.get("tab_size", 4)
            result = text.replace(" " * tab_size, "\t")
        else:
            raise ValueError(f"Unknown transform_type: {transform_type}")

        write_errors = params.get("errors") or "strict"
        if write_errors not in ("strict", "replace", "ignore"):
            write_errors = "strict"

        self._write_file(file_path, result, enc, write_errors)
        return {
            "success": True,
            "file_path": str(file_path),
            "transform_type": transform_type,
            "original_chars": len(text),
            "result_chars": len(result),
        }

    def _extract(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        err = params.get("errors") or "replace"
        text, enc, _ = self._read_text(file_path, params.get("encoding"), err)
        lines = text.splitlines()

        start_line = params.get("start_line")
        end_line = params.get("end_line")
        pattern = params.get("pattern")
        start_marker = params.get("start_marker")
        end_marker = params.get("end_marker")

        if start_line and end_line:
            s = max(0, start_line - 1)
            e = min(len(lines), end_line)
            extracted = lines[s:e]
            return {
                "file": str(file_path),
                "method": "line_range",
                "start_line": start_line,
                "end_line": end_line,
                "extracted": "\n".join(extracted),
                "line_count": len(extracted),
            }
        elif start_marker and end_marker:
            start_re = _compile_pattern(start_marker, params.get("regex_flags"))
            end_re = _compile_pattern(end_marker, params.get("regex_flags"))
            extracting = False
            extracted: list[str] = []
            for line in lines:
                if not extracting and start_re.search(line):
                    extracting = True
                    extracted.append(line)
                elif extracting:
                    extracted.append(line)
                    if end_re.search(line):
                        extracting = False
            return {
                "file": str(file_path),
                "method": "markers",
                "start_marker": start_marker,
                "end_marker": end_marker,
                "extracted": "\n".join(extracted),
                "line_count": len(extracted),
            }
        elif pattern:
            compiled = _compile_pattern(pattern, params.get("regex_flags"))
            matching = [line for line in lines if compiled.search(line)]
            return {
                "file": str(file_path),
                "method": "pattern",
                "pattern": pattern,
                "extracted": "\n".join(matching),
                "line_count": len(matching),
            }
        else:
            raise ValueError("extract requires start_line+end_line, start_marker+end_marker, or pattern")

    def _split(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        err = params.get("errors") or "replace"
        text, enc, _ = self._read_text(file_path, params.get("encoding"), err)

        output_dir = params.get("output_dir")
        if not output_dir:
            output_dir = str(file_path.parent / f"{file_path.stem}_parts")

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        delimiter = params.get("delimiter")
        chunk_lines = params.get("chunk_lines")

        parts: list[str] = []
        if chunk_lines:
            lines = text.splitlines(keepends=True)
            for i in range(0, len(lines), chunk_lines):
                parts.append("".join(lines[i:i + chunk_lines]))
        elif delimiter:
            compiled = _compile_pattern(delimiter, params.get("regex_flags"))
            parts = compiled.split(text)
            parts = [p for p in parts if p.strip()]
        else:
            parts = re.split(r"\n---\n|\f", text)
            parts = [p.strip() for p in parts if p.strip()]

        suffix = file_path.suffix or ".txt"
        written_files: list[str] = []
        for i, part in enumerate(parts, 1):
            part_path = out_path / f"part_{i:03d}{suffix}"
            part_path.write_text(part, encoding=enc)
            written_files.append(str(part_path))

        return {
            "success": True,
            "source_file": str(file_path),
            "output_dir": str(out_path),
            "parts_count": len(parts),
            "files": written_files,
        }

    def _join(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        source_files = params.get("source_files")
        if not source_files:
            raise ValueError("'source_files' is required for join operation")

        separator = params.get("separator", "\n")
        enc = (params.get("encoding") or "utf-8").strip()
        err = params.get("errors") or "replace"

        parts: list[str] = []
        for fp in source_files:
            p = Path(fp).expanduser().resolve()
            if not p.exists():
                raise FileNotFoundError(f"Source file not found: {fp}")
            text, _, _ = self._read_text(p, params.get("encoding"), err)
            parts.append(text.rstrip("\n"))

        joined = separator.join(parts) + "\n"

        write_errors = params.get("errors") or "strict"
        if write_errors not in ("strict", "replace", "ignore"):
            write_errors = "strict"

        self._write_file(file_path, joined, enc, write_errors)
        return {
            "success": True,
            "file_path": str(file_path),
            "files_joined": len(source_files),
            "total_chars": len(joined),
        }

    def _stats(self, file_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        err = params.get("errors") or "replace"
        text, enc, meta = self._read_text(file_path, params.get("encoding"), err)
        lines = text.splitlines()
        words = text.split()
        non_empty = sum(1 for ln in lines if ln.strip())

        char_freq: dict[str, int] = {}
        for c in text[:50000]:
            if c.isprintable() and not c.isspace():
                char_freq[c] = char_freq.get(c, 0) + 1
        top_chars = sorted(char_freq.items(), key=lambda x: x[1], reverse=True)[:20]

        return {
            "file": str(file_path),
            "encoding": enc,
            "decode": meta,
            "size_bytes": file_path.stat().st_size,
            "line_count": len(lines),
            "non_empty_lines": non_empty,
            "blank_lines": len(lines) - non_empty,
            "word_count": len(words),
            "char_count": len(text),
            "avg_line_length": round(len(text) / max(len(lines), 1), 1),
            "max_line_length": max((len(ln) for ln in lines), default=0),
            "line_endings": _line_ending_breakdown(text),
            "top_characters": top_chars,
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
