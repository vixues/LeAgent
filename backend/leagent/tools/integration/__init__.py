"""Integration tools for LeAgent.

This module provides tools for integrating with external systems including:
- OA systems (API, import, export)
- Email sending via SMTP
- Notifications (DingTalk, Feishu, WeChat Work)
- External API requests

Example:
    >>> from leagent.tools.integration import (
    ...     OAApiTool,
    ...     EmailSendTool,
    ...     NotificationTool,
    ...     ExternalApiTool,
    ... )
    >>>
    >>> # Send a notification to DingTalk
    >>> tool = NotificationTool()
    >>> result = await tool.run({
    ...     "channel": "dingtalk",
    ...     "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxx",
    ...     "content": "Task completed successfully",
    ... }, context)
"""

try:
    from leagent.tools.integration.email_send import (
        EmailBatchSendTool,
        EmailContentType,
        EmailPriority,
        EmailSendTool,
    )
except ImportError:
    EmailBatchSendTool = None  # type: ignore[assignment,misc]
    EmailContentType = None  # type: ignore[assignment,misc]
    EmailPriority = None  # type: ignore[assignment,misc]
    EmailSendTool = None  # type: ignore[assignment,misc]

from leagent.tools.integration.external_api import (
    AuthType,
    ContentType,
    ExternalApiTool,
)
from leagent.tools.integration.notification import (
    BatchNotificationTool,
    MessageType,
    NotificationChannel,
    NotificationPriority,
    NotificationTool,
    normalize_workflow_notification_params,
)
from leagent.tools.integration.speech_to_text import SpeechToTextTool
from leagent.tools.integration.oa_api import (
    OAApiTool,
    OAAuthType,
    OAOperation,
)
from leagent.tools.integration.oa_export import (
    ExportDataType,
    ExportFormat,
    ExportStatus,
    OAExportTool,
)
from leagent.tools.integration.oa_import import (
    ImportDataType,
    ImportSourceType,
    OAImportTool,
)

try:
    from leagent.tools.integration.configure_settings import ConfigureSettingsTool
except ImportError:
    ConfigureSettingsTool = None  # type: ignore[assignment,misc]

__all__ = [
    # OA API
    "OAApiTool",
    "OAAuthType",
    "OAOperation",
    # OA Import
    "OAImportTool",
    "ImportSourceType",
    "ImportDataType",
    # OA Export
    "OAExportTool",
    "ExportFormat",
    "ExportDataType",
    "ExportStatus",
    # Email
    "EmailSendTool",
    "EmailBatchSendTool",
    "EmailContentType",
    "EmailPriority",
    # Notification
    "NotificationTool",
    "BatchNotificationTool",
    "NotificationChannel",
    "NotificationPriority",
    "MessageType",
    "normalize_workflow_notification_params",
    # Speech
    "SpeechToTextTool",
    # External API
    "ExternalApiTool",
    "AuthType",
    "ContentType",
    # Settings
    "ConfigureSettingsTool",
]
