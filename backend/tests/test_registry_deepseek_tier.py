"""Registry helpers for DeepSeek tier routing."""

from leagent.llm.registry import _endpoint_hostname_is_deepseek


def test_endpoint_hostname_detects_deepseek() -> None:
    assert _endpoint_hostname_is_deepseek("https://api.deepseek.com/v1")
    assert _endpoint_hostname_is_deepseek("https://api.deepseek.com")


def test_endpoint_hostname_non_deepseek() -> None:
    assert not _endpoint_hostname_is_deepseek("https://dashscope.aliyuncs.com/compatible-mode/v1")
    assert not _endpoint_hostname_is_deepseek("")
