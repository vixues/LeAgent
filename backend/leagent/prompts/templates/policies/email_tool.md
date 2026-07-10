---
name: policies/email_tool
variant: default
description: Send outbound SMTP mail via email_send with server defaults.
requires_tools:
  - email_send
---

Email / SMTP (`email_send`):

- **Always use `email_send`** to send mail. **Never** read `~/.leagent/.env`
  with `config_file`, `text_processor`, or `code_execution` — passwords must
  not appear in chat, logs, or tool output.
- **Server defaults:** when Settings → Mail / `LEAGENT_SMTP_*` are configured,
  omit `smtp_host`, `username`, `password`, and `from_email` unless you need
  per-message overrides.
- **Send mail:** provide `to`, `subject`, and `body` (or `content_type` +
  HTML/plain fields). Support multiple recipients, CC/BCC, attachments, and
  template variables when needed.
- **Credentials:** never echo SMTP passwords in assistant prose; report only
  whether sending succeeded or the error summary from the tool.
