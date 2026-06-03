"""Tests for artifact error tracker code recovery directives."""

from leagent.context.artifact_error_tracker import ArtifactError, ArtifactErrorTracker


def test_code_syntax_directive_prefers_workspace_edit() -> None:
    tracker = ArtifactErrorTracker()
    tracker.record_error(
        ArtifactError(
            artifact_id="tc1",
            artifact_type="code",
            error_message="invalid syntax",
            source_tool_call_id="call-1",
            turn_index=0,
            error_type="syntax",
        )
    )
    directives = tracker.get_regeneration_directives()
    assert len(directives) == 1
    assert "code_workspace_edit" in directives[0]
    assert "reset_workspace" not in directives[0]


def test_code_escalates_after_repeated_failures() -> None:
    tracker = ArtifactErrorTracker()
    for _ in range(3):
        tracker.record_error(
            ArtifactError(
                artifact_id="tc1",
                artifact_type="code",
                error_message="still broken",
                source_tool_call_id="call-1",
                turn_index=0,
                error_type="runtime",
            )
        )
    directives = tracker.get_regeneration_directives()
    assert "reset_workspace" in directives[0]
