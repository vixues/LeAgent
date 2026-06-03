"""Task-based routing exports.

The previous complexity-tier router has been removed in v2. Import
``TaskResolver`` and ``ModelTask`` from here only as a convenience while code is
being migrated to ``leagent.llm.task_resolver`` directly.
"""

from leagent.llm.model_spec import ModelTask, ResolvedModel
from leagent.llm.task_resolver import TaskResolver

__all__ = ["ModelTask", "ResolvedModel", "TaskResolver"]
