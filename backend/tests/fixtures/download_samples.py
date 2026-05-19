"""Download real-world sample files from public URLs for integration testing.

Usage
─────
Run once before the test suite to populate the cache:

    python -m pytest tests/ -m network          # run network tests directly
    python tests/fixtures/download_samples.py   # or pre-download manually

Tests that require downloaded files are marked ``@pytest.mark.network`` and
are skipped automatically when the files are absent or the marker is excluded.

Cache location
──────────────
Files are stored in ``tests/fixtures/_cache/``.  Add this directory to
``.gitignore`` to keep binaries out of version control.
"""

from __future__ import annotations

import hashlib
import logging
import urllib.request
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "_cache"

TIMEOUT = 30  # seconds per download


class SampleFile(NamedTuple):
    name: str
    url: str
    min_bytes: int = 1024  # sanity-check: downloaded file must be at least this large


# ---------------------------------------------------------------------------
# File catalogue
# All URLs point to CDN-hosted, publicly accessible, stable files.
# ---------------------------------------------------------------------------

SAMPLE_FILES: list[SampleFile] = [
    # ── PDF ─────────────────────────────────────────────────────────────────
    SampleFile(
        "real_world.pdf",
        "https://www.w3.org/WAI/WCAG21/Techniques/pdf/pdf-sample.pdf",
        min_bytes=2_000,
    ),
    # ── DOCX ────────────────────────────────────────────────────────────────
    SampleFile(
        "real_world.docx",
        "https://filesamples.com/samples/document/docx/sample1.docx",
        min_bytes=5_000,
    ),
    # ── XLSX ────────────────────────────────────────────────────────────────
    SampleFile(
        "real_world.xlsx",
        "https://filesamples.com/samples/document/xlsx/sample1.xlsx",
        min_bytes=5_000,
    ),
    # ── XLS (legacy) ────────────────────────────────────────────────────────
    SampleFile(
        "real_world.xls",
        "https://filesamples.com/samples/document/xls/sample1.xls",
        min_bytes=5_000,
    ),
    # ── CSV ─────────────────────────────────────────────────────────────────
    SampleFile(
        "real_world.csv",
        "https://raw.githubusercontent.com/datasets/gdp/main/data/gdp.csv",
        min_bytes=1_000,
    ),
    # ── HTML ────────────────────────────────────────────────────────────────
    SampleFile(
        "real_world.html",
        "https://www.w3.org/TR/html401/html40.txt",   # plain text but large/real
        min_bytes=5_000,
    ),
    # ── Markdown ────────────────────────────────────────────────────────────
    SampleFile(
        "real_world.md",
        "https://raw.githubusercontent.com/commonmark/commonmark-spec/master/spec.txt",
        min_bytes=10_000,
    ),
    # ── JSON ────────────────────────────────────────────────────────────────
    SampleFile(
        "real_world.json",
        "https://raw.githubusercontent.com/datasets/gdp/main/datapackage.json",
        min_bytes=500,
    ),
    # ── YAML ────────────────────────────────────────────────────────────────
    SampleFile(
        "real_world.yaml",
        "https://raw.githubusercontent.com/OAI/OpenAPI-Specification/main/examples/v3.0/petstore.yaml",
        min_bytes=1_000,
    ),
    # ── PNG ─────────────────────────────────────────────────────────────────
    SampleFile(
        "real_world.png",
        "https://www.w3.org/Graphics/PNG/nurbcup2si.png",
        min_bytes=2_000,
    ),
    # ── JPEG ────────────────────────────────────────────────────────────────
    SampleFile(
        "real_world.jpg",
        "https://www.w3.org/People/Bos/Stylesheets/Images/button.jpg",
        min_bytes=1_000,
    ),
    # ── GIF ─────────────────────────────────────────────────────────────────
    SampleFile(
        "real_world.gif",
        "https://www.w3.org/People/Bos/Stylesheets/Images/w3c.gif",
        min_bytes=500,
    ),
    # ── ZIP ─────────────────────────────────────────────────────────────────
    SampleFile(
        "real_world.zip",
        "https://filesamples.com/samples/document/txt/sample1.txt.zip",
        min_bytes=1_000,
    ),
    # ── SQL ─────────────────────────────────────────────────────────────────
    SampleFile(
        "real_world.sql",
        "https://raw.githubusercontent.com/harness/gitness/main/app/store/database/migrate/sqlite/0001_create_core_tables.up.sql",
        min_bytes=500,
    ),
    # ── XML ─────────────────────────────────────────────────────────────────
    SampleFile(
        "real_world.xml",
        "https://www.w3schools.com/xml/cd_catalog.xml",
        min_bytes=500,
    ),
]


def download_all(force: bool = False) -> dict[str, Path]:
    """Download all sample files and return a mapping of name → local Path.

    Args:
        force: Re-download even if the file already exists.

    Returns:
        Dict mapping logical file name to its local Path.
        Files that fail to download are excluded from the result.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    for sf in SAMPLE_FILES:
        dest = CACHE_DIR / sf.name
        if dest.exists() and not force:
            if dest.stat().st_size >= sf.min_bytes:
                logger.info("Cache hit: %s (%d bytes)", sf.name, dest.stat().st_size)
                paths[sf.name] = dest
                continue
            else:
                logger.warning(
                    "Cached file too small (%d < %d), re-downloading: %s",
                    dest.stat().st_size, sf.min_bytes, sf.name,
                )

        logger.info("Downloading %s …", sf.url)
        try:
            req = urllib.request.Request(
                sf.url,
                headers={"User-Agent": "LeAgent-TestSuite/1.0"},
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310
                data = resp.read()

            if len(data) < sf.min_bytes:
                logger.warning(
                    "Downloaded %s is too small (%d bytes, expected >= %d); skipping",
                    sf.name, len(data), sf.min_bytes,
                )
                continue

            dest.write_bytes(data)
            sha = hashlib.sha256(data).hexdigest()[:12]
            logger.info("Saved %s (%d bytes, sha256=%.12s)", sf.name, len(data), sha)
            paths[sf.name] = dest

        except Exception as exc:
            logger.warning("Failed to download %s: %s", sf.name, exc)

    return paths


def get_cached_path(name: str) -> Path | None:
    """Return the cached path for a named sample file, or None if absent."""
    path = CACHE_DIR / name
    return path if path.exists() and path.stat().st_size > 0 else None


def list_cached() -> list[Path]:
    """Return all files currently in the cache directory."""
    if not CACHE_DIR.exists():
        return []
    return sorted(CACHE_DIR.iterdir())


# ---------------------------------------------------------------------------
# pytest fixtures for network tests
# ---------------------------------------------------------------------------

try:
    import pytest

    def _network_fixture(name: str):
        @pytest.fixture(scope="session")
        def _fixture():
            path = get_cached_path(name)
            if path is None:
                pytest.skip(f"Real-world sample not cached: {name} — run download_samples.py first")
            return path
        _fixture.__name__ = f"real_{name.replace('.', '_').replace('-', '_')}"
        return _fixture

    real_pdf   = _network_fixture("real_world.pdf")
    real_docx  = _network_fixture("real_world.docx")
    real_xlsx  = _network_fixture("real_world.xlsx")
    real_xls   = _network_fixture("real_world.xls")
    real_csv   = _network_fixture("real_world.csv")
    real_html  = _network_fixture("real_world.html")
    real_md    = _network_fixture("real_world.md")
    real_json  = _network_fixture("real_world.json")
    real_yaml  = _network_fixture("real_world.yaml")
    real_png   = _network_fixture("real_world.png")
    real_jpg   = _network_fixture("real_world.jpg")
    real_gif   = _network_fixture("real_world.gif")
    real_zip   = _network_fixture("real_world.zip")
    real_sql   = _network_fixture("real_world.sql")
    real_xml   = _network_fixture("real_world.xml")

except ImportError:
    pass  # running as a standalone script


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)-8s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Download LeAgent test sample files")
    parser.add_argument("--force", action="store_true", help="Re-download even if cached")
    parser.add_argument("--list", action="store_true", help="List cached files and exit")
    args = parser.parse_args()

    if args.list:
        cached = list_cached()
        if cached:
            print(f"Cached files in {CACHE_DIR}:")
            for p in cached:
                print(f"  {p.name:40s}  {p.stat().st_size:>10,} bytes")
        else:
            print("No cached files found.")
        sys.exit(0)

    results = download_all(force=args.force)

    print(f"\n{'─' * 60}")
    print(f"Downloaded {len(results)}/{len(SAMPLE_FILES)} files to {CACHE_DIR}")
    print(f"{'─' * 60}")
    for name, path in results.items():
        print(f"  ✓  {name:40s}  {path.stat().st_size:>10,} bytes")

    failed = [sf.name for sf in SAMPLE_FILES if sf.name not in results]
    if failed:
        print(f"\nFailed ({len(failed)}):")
        for name in failed:
            print(f"  ✗  {name}")
        sys.exit(1)
