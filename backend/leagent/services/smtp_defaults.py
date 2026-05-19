"""Merge server-wide SMTP defaults from Settings into tool parameters."""

from __future__ import annotations

from typing import Any

def _str_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def merge_smtp_defaults(params: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``params`` with missing SMTP fields filled from ``get_settings()``.

    Explicit non-empty tool arguments always win.
    """
    from leagent.config.settings import get_settings

    s = get_settings()
    out = dict(params)

    if _str_missing(out.get("smtp_host")) and (s.smtp_host or "").strip():
        out["smtp_host"] = s.smtp_host.strip()

    if out.get("smtp_port") is None or (isinstance(out.get("smtp_port"), str) and not str(out["smtp_port"]).strip()):
        out["smtp_port"] = int(s.smtp_port) if s.smtp_port else 587
    elif isinstance(out["smtp_port"], str):
        out["smtp_port"] = int(out["smtp_port"])

    if "use_tls" not in out:
        out["use_tls"] = bool(s.smtp_use_tls)
    if "use_ssl" not in out:
        out["use_ssl"] = bool(s.smtp_use_ssl)

    if _str_missing(out.get("username")) and (s.smtp_username or "").strip():
        out["username"] = s.smtp_username.strip()
    if _str_missing(out.get("password")) and (s.smtp_password or "").strip():
        out["password"] = s.smtp_password

    if _str_missing(out.get("from_email")) and (s.smtp_from_email or "").strip():
        out["from_email"] = s.smtp_from_email.strip()
    if "from_name" not in params:
        out["from_name"] = (s.smtp_from_name or "").strip()

    return out


async def check_smtp_connection(merged: dict[str, Any]) -> None:
    """Connect (STARTTLS/SSL) and optionally login; then disconnect.

    Raises ``RuntimeError`` if ``aiosmtplib`` is not installed.
    Raises ``Exception`` subclasses from ``aiosmtplib`` on SMTP failures.
    """
    try:
        import aiosmtplib
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "The mail test requires the optional dependency 'aiosmtplib'. "
            "Install it with `pip install aiosmtplib`."
        ) from exc

    host = (merged.get("smtp_host") or "").strip()
    if not host:
        raise ValueError("smtp_host is not configured")
    port = int(merged.get("smtp_port", 587))
    use_ssl = bool(merged.get("use_ssl", False))
    use_tls = bool(merged.get("use_tls", True))
    username = (merged.get("username") or "").strip()
    password = merged.get("password") or ""

    smtp = aiosmtplib.SMTP(hostname=host, port=port, timeout=25.0)
    try:
        if use_ssl:
            await smtp.connect(use_tls=True)
        else:
            await smtp.connect()
            if use_tls:
                await smtp.starttls()
        if username and password:
            await smtp.login(username, password)
    finally:
        try:
            await smtp.quit()
        except Exception:
            pass


async def send_smtp_test_message(merged: dict[str, Any], to_addr: str) -> None:
    """Send a minimal plain-text message (requires ``aiosmtplib``)."""
    try:
        import aiosmtplib
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The mail test requires the optional dependency 'aiosmtplib'. "
            "Install it with `pip install aiosmtplib`."
        ) from exc

    from email.mime.text import MIMEText
    from email.utils import formataddr, formatdate

    host = (merged.get("smtp_host") or "").strip()
    if not host:
        raise ValueError("smtp_host is not configured")
    from_email = (merged.get("from_email") or "").strip()
    if not from_email:
        raise ValueError("from_email is not configured")
    from_name = (merged.get("from_name") or "").strip()
    port = int(merged.get("smtp_port", 587))
    use_ssl = bool(merged.get("use_ssl", False))
    use_tls = bool(merged.get("use_tls", True))
    username = merged.get("username")
    password = merged.get("password")

    msg = MIMEText("LeAgent SMTP connectivity test.", "plain", "utf-8")
    msg["Subject"] = "LeAgent SMTP test"
    msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
    msg["To"] = to_addr
    msg["Date"] = formatdate(localtime=True)

    smtp_kwargs: dict[str, Any] = {
        "hostname": host,
        "port": port,
        "timeout": 60.0,
    }
    if use_ssl:
        smtp_kwargs["use_tls"] = True
    elif use_tls:
        smtp_kwargs["start_tls"] = True
    if username and password:
        smtp_kwargs["username"] = username
        smtp_kwargs["password"] = password

    await aiosmtplib.send(
        msg,
        sender=from_email,
        recipients=[to_addr],
        **smtp_kwargs,
    )
