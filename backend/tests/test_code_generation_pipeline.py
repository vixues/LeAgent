"""Tests for CodeArtifact, CodeArtifactRegistry, and CodeGenerationPipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from leagent.code.artifacts import (
    ArtifactKind,
    CodeArtifact,
    CodeArtifactRegistry,
)


# --------------------------------------------------------------------------- #
# CodeArtifact
# --------------------------------------------------------------------------- #


class TestCodeArtifact:
    def test_basic_creation(self) -> None:
        art = CodeArtifact(
            kind=ArtifactKind.EXECUTE,
            language="python",
            source="print('hello')",
            origin_tool="code_execution",
            session_id="s1",
        )
        assert art.kind == ArtifactKind.EXECUTE
        assert art.language == "python"
        assert art.source == "print('hello')"
        assert art.origin_tool == "code_execution"
        assert art.session_id == "s1"
        assert len(art.artifact_id) == 32  # uuid4().hex
        assert art.target_path is None
        assert art.syntax_valid is None
        assert art.diagnostics == []
        assert art.metadata == {}

    def test_to_dict(self) -> None:
        art = CodeArtifact(
            kind=ArtifactKind.FILE_WRITE,
            language="typescript",
            source="const x = 1;",
            origin_tool="project_write",
            session_id="s2",
            target_path="src/index.ts",
            syntax_valid=True,
        )
        d = art.to_dict()
        assert d["kind"] == "file_write"
        assert d["language"] == "typescript"
        assert d["origin_tool"] == "project_write"
        assert d["target_path"] == "src/index.ts"
        assert d["syntax_valid"] is True
        assert d["source_length"] == len("const x = 1;")
        assert "source" not in d  # source is not leaked

    def test_artifact_kind_values(self) -> None:
        assert ArtifactKind.EXECUTE.value == "execute"
        assert ArtifactKind.FILE_WRITE.value == "file_write"
        assert ArtifactKind.FILE_EDIT.value == "file_edit"
        assert ArtifactKind.FILE_PATCH.value == "file_patch"
        assert ArtifactKind.SNIPPET.value == "snippet"


# --------------------------------------------------------------------------- #
# CodeArtifactRegistry
# --------------------------------------------------------------------------- #


class TestCodeArtifactRegistry:
    def test_register_and_get(self) -> None:
        reg = CodeArtifactRegistry()
        art = CodeArtifact(
            kind=ArtifactKind.EXECUTE,
            language="python",
            source="x=1",
            origin_tool="code_execution",
            session_id="s1",
        )
        reg.register(art)
        assert reg.get(art.artifact_id) is art

    def test_get_missing_returns_none(self) -> None:
        reg = CodeArtifactRegistry()
        assert reg.get("nonexistent") is None

    def test_list_for_session(self) -> None:
        reg = CodeArtifactRegistry()
        a1 = CodeArtifact(
            kind=ArtifactKind.EXECUTE,
            language="python",
            source="1",
            origin_tool="t",
            session_id="s1",
        )
        a2 = CodeArtifact(
            kind=ArtifactKind.FILE_WRITE,
            language="python",
            source="2",
            origin_tool="t",
            session_id="s1",
        )
        a3 = CodeArtifact(
            kind=ArtifactKind.SNIPPET,
            language="python",
            source="3",
            origin_tool="t",
            session_id="s2",
        )
        reg.register(a1)
        reg.register(a2)
        reg.register(a3)
        s1_list = reg.list_for_session("s1")
        assert len(s1_list) == 2
        assert s1_list[0].artifact_id == a1.artifact_id
        assert s1_list[1].artifact_id == a2.artifact_id
        assert len(reg.list_for_session("s2")) == 1
        assert len(reg.list_for_session("s_unknown")) == 0

    def test_clear_session(self) -> None:
        reg = CodeArtifactRegistry()
        art = CodeArtifact(
            kind=ArtifactKind.EXECUTE,
            language="python",
            source="x",
            origin_tool="t",
            session_id="s1",
        )
        reg.register(art)
        assert reg.get(art.artifact_id) is not None
        reg.clear_session("s1")
        assert reg.get(art.artifact_id) is None
        assert reg.list_for_session("s1") == []

    def test_eviction_on_max(self) -> None:
        reg = CodeArtifactRegistry()
        from leagent.code.artifacts import _MAX_ARTIFACTS_PER_SESSION

        first_ids: list[str] = []
        for i in range(_MAX_ARTIFACTS_PER_SESSION + 5):
            art = CodeArtifact(
                kind=ArtifactKind.EXECUTE,
                language="python",
                source=str(i),
                origin_tool="t",
                session_id="s1",
            )
            reg.register(art)
            if i < 5:
                first_ids.append(art.artifact_id)

        # The first 5 should have been evicted
        for fid in first_ids:
            assert reg.get(fid) is None

        session_list = reg.list_for_session("s1")
        assert len(session_list) == _MAX_ARTIFACTS_PER_SESSION


# --------------------------------------------------------------------------- #
# CodeGenerationPipeline
# --------------------------------------------------------------------------- #


@dataclass
class _FakeToolContext:
    """Minimal mock of ToolContext for pipeline tests."""

    session_id: str = "test-session"
    user_id: str = "test-user"
    extra: dict[str, Any] = field(default_factory=dict)


class TestCodeGenerationPipeline:
    @pytest.mark.asyncio
    async def test_prepare_creates_artifact(self) -> None:
        from leagent.code.pipeline import CodeGenerationPipeline

        reg = CodeArtifactRegistry()
        pipe = CodeGenerationPipeline(reg)
        ctx = _FakeToolContext()

        art = await pipe.prepare(
            kind=ArtifactKind.EXECUTE,
            source="print('hello')",
            language="python",
            origin_tool="code_execution",
            context=ctx,
        )
        assert art.kind == ArtifactKind.EXECUTE
        assert art.language == "python"
        assert art.session_id == "test-session"
        assert art.syntax_valid is True
        assert reg.get(art.artifact_id) is art

    @pytest.mark.asyncio
    async def test_prepare_detects_syntax_error(self) -> None:
        from leagent.code.pipeline import CodeGenerationPipeline

        reg = CodeArtifactRegistry()
        pipe = CodeGenerationPipeline(reg)
        ctx = _FakeToolContext()

        art = await pipe.prepare(
            kind=ArtifactKind.EXECUTE,
            source="def foo(\n    pass",
            language="python",
            origin_tool="code_execution",
            context=ctx,
        )
        assert art.syntax_valid is False
        assert len(art.diagnostics) > 0

    @pytest.mark.asyncio
    async def test_should_block_execute_with_syntax_error(self) -> None:
        from leagent.code.pipeline import CodeGenerationPipeline

        reg = CodeArtifactRegistry()
        pipe = CodeGenerationPipeline(reg)
        ctx = _FakeToolContext()

        art = await pipe.prepare(
            kind=ArtifactKind.EXECUTE,
            source="def foo(\n    pass",
            language="python",
            origin_tool="code_execution",
            context=ctx,
        )
        assert pipe.should_block(art) is True

    @pytest.mark.asyncio
    async def test_should_not_block_file_write_with_syntax_error(self) -> None:
        from leagent.code.pipeline import CodeGenerationPipeline

        reg = CodeArtifactRegistry()
        pipe = CodeGenerationPipeline(reg)
        ctx = _FakeToolContext()

        art = await pipe.prepare(
            kind=ArtifactKind.FILE_WRITE,
            source="def foo(\n    pass",
            language="python",
            origin_tool="project_write",
            context=ctx,
            target_path="broken.py",
        )
        assert art.syntax_valid is False
        assert pipe.should_block(art) is False

    @pytest.mark.asyncio
    async def test_skip_validation(self) -> None:
        from leagent.code.pipeline import CodeGenerationPipeline

        reg = CodeArtifactRegistry()
        pipe = CodeGenerationPipeline(reg)
        ctx = _FakeToolContext()

        art = await pipe.prepare(
            kind=ArtifactKind.FILE_PATCH,
            source="--- a/foo.py\n+++ b/foo.py",
            language="diff",
            origin_tool="project_apply_patch",
            context=ctx,
            skip_validation=True,
        )
        assert art.syntax_valid is None
        assert art.diagnostics == []

    @pytest.mark.asyncio
    async def test_auto_language_detection(self) -> None:
        from leagent.code.pipeline import CodeGenerationPipeline

        reg = CodeArtifactRegistry()
        pipe = CodeGenerationPipeline(reg)
        ctx = _FakeToolContext()

        art = await pipe.prepare(
            kind=ArtifactKind.FILE_WRITE,
            source='{"key": "value"}',
            language="auto",
            origin_tool="project_write",
            context=ctx,
            target_path="config/settings.json",
        )
        assert art.language == "json"
        assert art.syntax_valid is True

    @pytest.mark.asyncio
    async def test_auto_language_unknown_extension(self) -> None:
        from leagent.code.pipeline import CodeGenerationPipeline

        reg = CodeArtifactRegistry()
        pipe = CodeGenerationPipeline(reg)
        ctx = _FakeToolContext()

        art = await pipe.prepare(
            kind=ArtifactKind.FILE_WRITE,
            source="hello world",
            language="auto",
            origin_tool="project_write",
            context=ctx,
            target_path="readme.xyz",
        )
        assert art.language == "text"

    @pytest.mark.asyncio
    async def test_metadata_passed_through(self) -> None:
        from leagent.code.pipeline import CodeGenerationPipeline

        reg = CodeArtifactRegistry()
        pipe = CodeGenerationPipeline(reg)
        ctx = _FakeToolContext()

        art = await pipe.prepare(
            kind=ArtifactKind.SNIPPET,
            source="x = 1",
            language="python",
            origin_tool="deepseek_fim",
            context=ctx,
            skip_validation=True,
            metadata={"model": "deepseek-v4-pro", "buffer_id": "default"},
        )
        assert art.metadata["model"] == "deepseek-v4-pro"
        assert art.metadata["buffer_id"] == "default"

    @pytest.mark.asyncio
    async def test_hook_fires_when_available(self) -> None:
        from leagent.code.pipeline import CodeGenerationPipeline

        reg = CodeArtifactRegistry()
        pipe = CodeGenerationPipeline(reg)

        fired: list[CodeArtifact] = []

        class _FakeHookManager:
            async def fire_code_artifact(self, artifact: CodeArtifact) -> None:
                fired.append(artifact)

        ctx = _FakeToolContext(extra={"hooks": _FakeHookManager()})

        art = await pipe.prepare(
            kind=ArtifactKind.EXECUTE,
            source="print(1)",
            language="python",
            origin_tool="code_execution",
            context=ctx,
        )
        assert len(fired) == 1
        assert fired[0].artifact_id == art.artifact_id

    @pytest.mark.asyncio
    async def test_hook_error_does_not_crash(self) -> None:
        from leagent.code.pipeline import CodeGenerationPipeline

        reg = CodeArtifactRegistry()
        pipe = CodeGenerationPipeline(reg)

        class _BrokenHookManager:
            async def fire_code_artifact(self, artifact: CodeArtifact) -> None:
                raise RuntimeError("hook exploded")

        ctx = _FakeToolContext(extra={"hooks": _BrokenHookManager()})

        art = await pipe.prepare(
            kind=ArtifactKind.EXECUTE,
            source="print(1)",
            language="python",
            origin_tool="code_execution",
            context=ctx,
        )
        assert art is not None
        assert reg.get(art.artifact_id) is art


# --------------------------------------------------------------------------- #
# get_pipeline helper
# --------------------------------------------------------------------------- #


class TestGetPipeline:
    def test_returns_pipeline_when_registry_present(self) -> None:
        from leagent.code.pipeline import get_pipeline, _CONTEXT_REGISTRY_KEY

        reg = CodeArtifactRegistry()
        ctx = _FakeToolContext(extra={_CONTEXT_REGISTRY_KEY: reg})
        pipe = get_pipeline(ctx)
        assert pipe is not None

    def test_returns_none_when_no_registry(self) -> None:
        from leagent.code.pipeline import get_pipeline

        ctx = _FakeToolContext(extra={})
        assert get_pipeline(ctx) is None

    def test_returns_none_when_no_extra(self) -> None:
        from leagent.code.pipeline import get_pipeline

        @dataclass
        class _MinimalContext:
            session_id: str = "s"

        assert get_pipeline(_MinimalContext()) is None
