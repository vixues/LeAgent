from __future__ import annotations

from pathlib import Path

from leagent.context.file_state import FileState


def test_record_and_get(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello")
    fs = FileState(max_entries=10, max_tokens=1000)
    rec = fs.record_read(f, tokens=5)
    assert rec.path == str(f.resolve())
    assert fs.has_record(f)
    assert not fs.has_changed(f)


def test_lru_eviction(tmp_path):
    fs = FileState(max_entries=2, max_tokens=10000)
    for i in range(3):
        p = tmp_path / f"{i}.txt"
        p.write_text(f"content{i}")
        fs.record_read(p, tokens=1)
    assert len(fs) == 2


def test_pin_prevents_eviction(tmp_path):
    fs = FileState(max_entries=2, max_tokens=10000)
    p0 = tmp_path / "0.txt"
    p0.write_text("zero")
    fs.record_read(p0, tokens=1)
    fs.pin(p0)
    for i in range(1, 4):
        p = tmp_path / f"{i}.txt"
        p.write_text(f"content{i}")
        fs.record_read(p, tokens=1)
    assert fs.has_record(p0)


def test_snapshot_roundtrip(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("data")
    fs = FileState()
    fs.record_read(f, tokens=10)
    snap = fs.snapshot()
    fs2 = FileState.from_snapshot(snap)
    assert len(fs2) == 1


def test_merge_from_brings_child_paths(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("a")
    b.write_text("b")
    parent = FileState(max_entries=10, max_tokens=10000)
    parent.record_read(a, tokens=1)
    child = FileState(max_entries=10, max_tokens=10000)
    child.record_read(b, tokens=2)
    parent.merge_from(child)
    assert parent.has_record(a)
    assert parent.has_record(b)
