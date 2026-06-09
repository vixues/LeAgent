"""Email Send Tool - Send emails via SMTP.

Provides email sending capabilities with support for HTML/plain text,
attachments, and template-based emails.
"""

from __future__ import annotations

import asyncio
import mimetypes
import re
from email.encoders import encode_base64
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from leagent.services.smtp_defaults import merge_smtp_defaults
from leagent.tools.base import BaseTool, NonRetryableToolError, ToolCategory, ToolContext

if TYPE_CHECKING:
    import aiosmtplib

logger = structlog.get_logger(__name__)


def _load_aiosmtplib() -> "aiosmtplib":
    """Import ``aiosmtplib`` lazily so the module loads without the optional dep.

    Raises a clear ``RuntimeError`` only when the email tool is actually invoked
    on a system where ``aiosmtplib`` is not installed (it is intentionally not
    in the desktop runtime requirements).
    """

    try:
        import aiosmtplib as _aiosmtplib
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "The 'email_send' tool requires the optional dependency 'aiosmtplib'. "
            "Install it with `pip install aiosmtplib` to enable SMTP email sending."
        ) from exc
    return _aiosmtplib


class EmailContentType(str, Enum):
    """Email content types."""

    PLAIN = "plain"
    HTML = "html"
    BOTH = "both"


class EmailPriority(str, Enum):
    """Email priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class EmailSendTool(BaseTool):
    """Tool for sending emails via SMTP.

    Features:
    - HTML and plain text support
    - Attachment handling (files and inline data)
    - Template-based emails with variable substitution
    - Multiple recipients (To, CC, BCC)
    - Priority levels
    - TLS/SSL encryption
    - Connection pooling for batch sends

    Example:
        >>> tool = EmailSendTool()
        >>> result = await tool.run({
        ...     "smtp_host": "smtp.company.com",
        ...     "smtp_port": 587,
        ...     "username": "sender@company.com",
        ...     "password": "secret",
        ...     "from_email": "sender@company.com",
        ...     "to": ["recipient@example.com"],
        ...     "subject": "Meeting Reminder",
        ...     "body": "<h1>Meeting Tomorrow</h1><p>Don't forget!</p>",
        ...     "content_type": "html"
        ... }, context)
    """

    name = "email_send"
    description = (
        "Send emails via SMTP with support for HTML/plain text content, "
        "attachments, templates, and multiple recipients. "
        "When the server has SMTP defaults (Settings → Mail / LEAGENT_SMTP_*), "
        "you may omit smtp_host, from_email, and related fields unless you need overrides."
    )
    category = ToolCategory.INTEGRATION
    version = "1.0.0"
    timeout_sec = 120
    max_retries = 2
    aliases = ["email", "send_email", "smtp"]
    search_hint = "email send SMTP HTML text attachment template recipient"
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = False
    interrupt_behavior = "block"
    max_result_size_chars = 50_000

    def _enforce_path_sandbox(
        self,
        params: dict[str, Any],
        context: "ToolContext",
    ) -> None:
        from leagent.file.sandbox import PathSandbox

        request_id = context.extra.get("request_id", context.session_id or "")
        for att in params.get("attachments") or []:
            if isinstance(att, dict):
                fp = att.get("path", "")
                if fp and isinstance(fp, str) and not fp.startswith("minio://"):
                    PathSandbox.resolve_safe(
                        fp, context=context, tool_name=self.name,
                        request_id=str(request_id),
                    )

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        to = (params or {}).get("to", "")
        return f"Sending email{f' to {to}' if to else ''}"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "smtp_host": {
                    "type": "string",
                    "description": "SMTP server hostname (optional if configured in Settings → Mail)",
                },
                "smtp_port": {
                    "type": "integer",
                    "description": "SMTP server port",
                    "default": 587,
                },
                "use_tls": {
                    "type": "boolean",
                    "description": "Use STARTTLS encryption",
                    "default": True,
                },
                "use_ssl": {
                    "type": "boolean",
                    "description": "Use SSL/TLS from the start (for port 465)",
                    "default": False,
                },
                "username": {
                    "type": "string",
                    "description": "SMTP authentication username",
                },
                "password": {
                    "type": "string",
                    "description": "SMTP authentication password",
                },
                "from_email": {
                    "type": "string",
                    "description": "Sender email address (optional if LEAGENT_SMTP_FROM_EMAIL is set)",
                },
                "from_name": {
                    "type": "string",
                    "description": "Sender display name",
                },
                "to": {
                    "type": "array",
                    "description": "Primary recipient email addresses",
                    "items": {"type": "string"},
                },
                "cc": {
                    "type": "array",
                    "description": "CC recipient email addresses",
                    "items": {"type": "string"},
                },
                "bcc": {
                    "type": "array",
                    "description": "BCC recipient email addresses",
                    "items": {"type": "string"},
                },
                "reply_to": {
                    "type": "string",
                    "description": "Reply-to email address",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line",
                },
                "body": {
                    "type": "string",
                    "description": "Email body content",
                },
                "content_type": {
                    "type": "string",
                    "enum": [ct.value for ct in EmailContentType],
                    "default": "plain",
                    "description": "Content type: plain, html, or both",
                },
                "plain_body": {
                    "type": "string",
                    "description": "Plain text body (for content_type='both')",
                },
                "template": {
                    "type": "string",
                    "description": "Email template with {{variable}} placeholders",
                },
                "template_variables": {
                    "type": "object",
                    "description": "Variables to substitute in template",
                },
                "attachments": {
                    "type": "array",
                    "description": "File attachments",
                    "items": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string"},
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                            "content_type": {"type": "string"},
                            "inline": {"type": "boolean"},
                            "content_id": {"type": "string"},
                        },
                        "required": ["filename"],
                    },
                },
                "priority": {
                    "type": "string",
                    "enum": [p.value for p in EmailPriority],
                    "default": "normal",
                    "description": "Email priority level",
                },
                "headers": {
                    "type": "object",
                    "description": "Custom email headers",
                },
                "message_id": {
                    "type": "string",
                    "description": "Custom Message-ID header",
                },
                "references": {
                    "type": "string",
                    "description": "References header for threading",
                },
                "in_reply_to": {
                    "type": "string",
                    "description": "In-Reply-To header for threading",
                },
            },
            "required": ["to", "subject"],
        }

    def _validate_email(self, email: str) -> bool:
        """Validate email address format."""
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, email))

    def _render_template(self, template: str, variables: dict[str, Any]) -> str:
        """Render template with variable substitution."""
        result = template
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            result = result.replace(placeholder, str(value) if value is not None else "")
        return result

    def _get_priority_headers(self, priority: str) -> dict[str, str]:
        """Get headers for email priority."""
        if priority == EmailPriority.HIGH.value:
            return {
                "X-Priority": "1",
                "X-MSMail-Priority": "High",
                "Importance": "High",
            }
        elif priority == EmailPriority.LOW.value:
            return {
                "X-Priority": "5",
                "X-MSMail-Priority": "Low",
                "Importance": "Low",
            }
        return {}

    async def _add_attachment(
        self,
        msg: MIMEMultipart,
        attachment: dict[str, Any],
        context: ToolContext,
    ) -> None:
        """Add attachment to email message."""
        filename = attachment["filename"]
        file_path = attachment.get("path")
        content = attachment.get("content")
        content_type = attachment.get("content_type")
        is_inline = attachment.get("inline", False)
        content_id = attachment.get("content_id")

        if file_path:
            if context.file_store and file_path.startswith("minio://"):
                bucket, key = file_path[8:].split("/", 1)
                response = context.file_store.get_object(bucket, key)
                file_data = response.read()
                response.close()
            else:
                path = Path(file_path)
                if not path.exists():
                    logger.warning("Attachment file not found", path=file_path)
                    return
                file_data = path.read_bytes()
        elif content:
            import base64

            file_data = base64.b64decode(content)
        else:
            logger.warning("Attachment has no path or content", filename=filename)
            return

        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = "application/octet-stream"

        maintype, subtype = content_type.split("/", 1)

        part = MIMEBase(maintype, subtype)
        part.set_payload(file_data)
        encode_base64(part)

        if is_inline and content_id:
            part.add_header("Content-ID", f"<{content_id}>")
            part.add_header("Content-Disposition", "inline", filename=filename)
        else:
            part.add_header(
                "Content-Disposition",
                "attachment",
                filename=filename,
            )

        msg.attach(part)

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Send email via SMTP.

        Args:
            params: Email parameters including SMTP config, recipients, and content.
            context: Tool execution context.

        Returns:
            Dictionary containing send status and message details.

        Raises:
            ValueError: If email parameters are invalid.
            RuntimeError: If ``aiosmtplib`` is not installed.
            aiosmtplib.SMTPException: If SMTP operations fail.
        """
        aiosmtplib = _load_aiosmtplib()

        params = merge_smtp_defaults(dict(params))

        if not (params.get("smtp_host") or "").strip():
            raise NonRetryableToolError(
                "smtp_host is missing: pass smtp_host or configure outbound SMTP in Settings → Mail."
            )
        if not (params.get("from_email") or "").strip():
            raise NonRetryableToolError(
                "from_email is missing: pass from_email or set LEAGENT_SMTP_FROM_EMAIL in Settings → Mail."
            )

        smtp_host = params["smtp_host"]
        smtp_port = params.get("smtp_port", 587)
        use_tls = params.get("use_tls", True)
        use_ssl = params.get("use_ssl", False)
        username = params.get("username")
        password = params.get("password")

        from_email = params["from_email"]
        from_name = params.get("from_name", "")
        to_list = params["to"]
        cc_list = params.get("cc", [])
        bcc_list = params.get("bcc", [])
        reply_to = params.get("reply_to")

        subject = params["subject"]
        body = params.get("body", "")
        content_type = params.get("content_type", EmailContentType.PLAIN.value)
        plain_body = params.get("plain_body")
        template = params.get("template")
        template_variables = params.get("template_variables", {})
        attachments = params.get("attachments", [])
        priority = params.get("priority", EmailPriority.NORMAL.value)
        custom_headers = params.get("headers", {})
        message_id = params.get("message_id")
        references = params.get("references")
        in_reply_to = params.get("in_reply_to")

        if not self._validate_email(from_email):
            raise ValueError(f"Invalid sender email: {from_email}")

        all_recipients = to_list + cc_list + bcc_list
        for email in all_recipients:
            if not self._validate_email(email):
                raise ValueError(f"Invalid recipient email: {email}")

        if template:
            body = self._render_template(template, template_variables)
            if plain_body:
                plain_body = self._render_template(plain_body, template_variables)

        has_attachments = bool(attachments)
        is_alternative = content_type == EmailContentType.BOTH.value

        if has_attachments:
            msg = MIMEMultipart("mixed")
            if is_alternative:
                alt_part = MIMEMultipart("alternative")
                msg.attach(alt_part)
            else:
                alt_part = msg
        elif is_alternative:
            msg = MIMEMultipart("alternative")
            alt_part = msg
        else:
            msg = MIMEMultipart()
            alt_part = msg

        if from_name:
            msg["From"] = formataddr((from_name, from_email))
        else:
            msg["From"] = from_email

        msg["To"] = ", ".join(to_list)
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)

        if reply_to:
            msg["Reply-To"] = reply_to
        if message_id:
            msg["Message-ID"] = message_id
        if references:
            msg["References"] = references
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to

        priority_headers = self._get_priority_headers(priority)
        for header, value in priority_headers.items():
            msg[header] = value

        for header, value in custom_headers.items():
            msg[header] = value

        if content_type == EmailContentType.PLAIN.value:
            alt_part.attach(MIMEText(body, "plain", "utf-8"))
        elif content_type == EmailContentType.HTML.value:
            alt_part.attach(MIMEText(body, "html", "utf-8"))
        elif content_type == EmailContentType.BOTH.value:
            if plain_body:
                alt_part.attach(MIMEText(plain_body, "plain", "utf-8"))
            else:
                from html import unescape
                import re as regex

                stripped = regex.sub(r"<[^>]+>", "", body)
                alt_part.attach(MIMEText(unescape(stripped), "plain", "utf-8"))
            alt_part.attach(MIMEText(body, "html", "utf-8"))

        for attachment in attachments:
            await self._add_attachment(msg, attachment, context)

        logger.info(
            "Sending email",
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            from_email=from_email,
            to=to_list,
            subject=subject,
            has_attachments=has_attachments,
        )

        try:
            smtp_kwargs: dict[str, Any] = {
                "hostname": smtp_host,
                "port": smtp_port,
                "timeout": self.timeout_sec,
            }

            if use_ssl:
                smtp_kwargs["use_tls"] = True
            elif use_tls:
                smtp_kwargs["start_tls"] = True

            if username and password:
                smtp_kwargs["username"] = username
                smtp_kwargs["password"] = password

            response = await aiosmtplib.send(
                msg,
                sender=from_email,
                recipients=all_recipients,
                **smtp_kwargs,
            )

            logger.info(
                "Email sent successfully",
                from_email=from_email,
                to=to_list,
                subject=subject,
            )

            return {
                "success": True,
                "message_id": msg.get("Message-ID"),
                "from": from_email,
                "to": to_list,
                "cc": cc_list,
                "bcc": bcc_list,
                "subject": subject,
                "content_type": content_type,
                "attachments_count": len(attachments),
                "smtp_response": str(response),
            }

        except aiosmtplib.SMTPException as e:
            logger.error(
                "Failed to send email",
                from_email=from_email,
                to=to_list,
                error=str(e),
            )
            raise


class EmailBatchSendTool(BaseTool):
    """Tool for sending batch emails with personalization.

    Features:
    - Send to multiple recipients with personalized content
    - Rate limiting to avoid SMTP throttling
    - Progress tracking
    - Partial success handling

    Example:
        >>> tool = EmailBatchSendTool()
        >>> result = await tool.run({
        ...     "smtp_host": "smtp.company.com",
        ...     "smtp_port": 587,
        ...     "username": "sender@company.com",
        ...     "password": "secret",
        ...     "from_email": "sender@company.com",
        ...     "recipients": [
        ...         {"email": "user1@example.com", "name": "User 1", "vars": {"code": "ABC"}},
        ...         {"email": "user2@example.com", "name": "User 2", "vars": {"code": "XYZ"}},
        ...     ],
        ...     "subject": "Your Code: {{code}}",
        ...     "template": "<h1>Hello {{name}}</h1><p>Your code is {{code}}</p>"
        ... }, context)
    """

    name = "email_batch_send"
    description = (
        "Send batch emails with personalization. Supports template variables "
        "per recipient, rate limiting, and progress tracking. "
        "SMTP host/from defaults apply when configured under Settings → Mail (LEAGENT_SMTP_*)."
    )
    category = ToolCategory.INTEGRATION
    version = "1.0.0"
    timeout_sec = 600
    max_retries = 1
    aliases = ["batch_email", "mass_email", "bulk_email"]
    search_hint = "email batch bulk send personalize template rate limit"
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = False
    interrupt_behavior = "block"
    max_result_size_chars = 50_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        count = len((params or {}).get("recipients", []))
        return f"Sending batch emails ({count} recipients)"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "smtp_host": {
                    "type": "string",
                    "description": "SMTP server hostname (optional if configured in Settings → Mail)",
                },
                "smtp_port": {
                    "type": "integer",
                    "description": "SMTP server port",
                    "default": 587,
                },
                "use_tls": {
                    "type": "boolean",
                    "default": True,
                },
                "use_ssl": {
                    "type": "boolean",
                    "default": False,
                },
                "username": {
                    "type": "string",
                },
                "password": {
                    "type": "string",
                },
                "from_email": {
                    "type": "string",
                    "description": "Sender email (optional if LEAGENT_SMTP_FROM_EMAIL is set)",
                },
                "from_name": {
                    "type": "string",
                },
                "recipients": {
                    "type": "array",
                    "description": "List of recipients with personalization",
                    "items": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string"},
                            "name": {"type": "string"},
                            "vars": {"type": "object"},
                        },
                        "required": ["email"],
                    },
                },
                "subject": {
                    "type": "string",
                    "description": "Subject template with {{variable}} placeholders",
                },
                "template": {
                    "type": "string",
                    "description": "Body template with {{variable}} placeholders",
                },
                "content_type": {
                    "type": "string",
                    "enum": ["plain", "html", "both"],
                    "default": "html",
                },
                "attachments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string"},
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["filename"],
                    },
                },
                "rate_limit": {
                    "type": "number",
                    "description": "Emails per second limit",
                    "default": 5,
                    "minimum": 0.1,
                    "maximum": 100,
                },
                "stop_on_error": {
                    "type": "boolean",
                    "default": False,
                },
            },
            "required": ["recipients", "subject", "template"],
        }

    def _render_template(self, template: str, variables: dict[str, Any]) -> str:
        """Render template with variable substitution."""
        result = template
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            result = result.replace(placeholder, str(value) if value is not None else "")
        return result

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Send batch emails with personalization.

        Args:
            params: Batch email parameters.
            context: Tool execution context.

        Returns:
            Dictionary containing batch send results and statistics.
        """
        params = merge_smtp_defaults(dict(params))
        if not (params.get("smtp_host") or "").strip():
            raise NonRetryableToolError(
                "smtp_host is missing: pass smtp_host or configure outbound SMTP in Settings → Mail."
            )
        if not (params.get("from_email") or "").strip():
            raise NonRetryableToolError(
                "from_email is missing: pass from_email or set LEAGENT_SMTP_FROM_EMAIL in Settings → Mail."
            )

        recipients = params["recipients"]
        subject_template = params["subject"]
        body_template = params["template"]
        rate_limit = params.get("rate_limit", 5)
        stop_on_error = params.get("stop_on_error", False)

        email_tool = EmailSendTool()
        results: list[dict[str, Any]] = []
        success_count = 0
        failed_count = 0

        delay = 1.0 / rate_limit

        for idx, recipient in enumerate(recipients):
            email = recipient["email"]
            name = recipient.get("name", "")
            vars_dict = recipient.get("vars", {})

            vars_dict["name"] = name
            vars_dict["email"] = email

            subject = self._render_template(subject_template, vars_dict)
            body = self._render_template(body_template, vars_dict)

            email_params = {
                "smtp_host": params["smtp_host"],
                "smtp_port": params.get("smtp_port", 587),
                "use_tls": params.get("use_tls", True),
                "use_ssl": params.get("use_ssl", False),
                "username": params.get("username"),
                "password": params.get("password"),
                "from_email": params["from_email"],
                "from_name": params.get("from_name", ""),
                "to": [email],
                "subject": subject,
                "body": body,
                "content_type": params.get("content_type", "html"),
                "attachments": params.get("attachments", []),
            }

            try:
                result = await email_tool.execute(email_params, context)
                results.append({
                    "email": email,
                    "status": "success",
                    "message_id": result.get("message_id"),
                })
                success_count += 1

            except Exception as e:
                logger.error("Failed to send email", email=email, error=str(e))
                results.append({
                    "email": email,
                    "status": "failed",
                    "error": str(e),
                })
                failed_count += 1

                if stop_on_error:
                    break

            if idx < len(recipients) - 1:
                await asyncio.sleep(delay)

        return {
            "success": failed_count == 0,
            "statistics": {
                "total": len(recipients),
                "success": success_count,
                "failed": failed_count,
            },
            "results": results,
        }
