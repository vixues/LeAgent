from __future__ import annotations

from leagent.services.execution.policies import (
    AgentPolicy,
    CronPolicy,
    ExecutionPolicy,
    WorkflowPolicy,
)


def test_execution_policy_factories_replace_subclasses() -> None:
    agent = ExecutionPolicy.agent()
    cron = ExecutionPolicy.cron()
    workflow = ExecutionPolicy.workflow()

    assert isinstance(agent, ExecutionPolicy)
    assert isinstance(cron, ExecutionPolicy)
    assert isinstance(workflow, ExecutionPolicy)
    assert agent.allow_free_shell is False
    assert cron.allow_free_shell is True
    assert workflow.max_timeout_sec == 1800.0


def test_compatibility_shims_return_execution_policy_instances() -> None:
    assert isinstance(AgentPolicy(), ExecutionPolicy)
    assert isinstance(CronPolicy(), ExecutionPolicy)
    assert isinstance(WorkflowPolicy(timeout_sec=10), ExecutionPolicy)
    assert WorkflowPolicy(timeout_sec=10).timeout_sec == 10
