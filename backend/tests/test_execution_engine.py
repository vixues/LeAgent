from __future__ import annotations

from leagent.services.execution.engine import ExecutionEngine


def test_execution_engine_initial_state() -> None:
    engine = ExecutionEngine(max_concurrent=3, max_per_session=2)
    assert engine.active_count == 0
    assert engine.total_executions == 0


def test_execution_engine_session_quota_checks() -> None:
    engine = ExecutionEngine(max_per_session=2)
    sid = "s-1"
    assert engine._check_session_quota(sid) is True  # noqa: SLF001
    engine._inc_session_count(sid)  # noqa: SLF001
    engine._inc_session_count(sid)  # noqa: SLF001
    assert engine._check_session_quota(sid) is False  # noqa: SLF001
    engine._dec_session_count(sid)  # noqa: SLF001
    assert engine._check_session_quota(sid) is True  # noqa: SLF001
