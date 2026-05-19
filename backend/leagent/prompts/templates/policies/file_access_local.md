---
name: policies/file_access_local
variant: default
description: File-access policy for the single-machine / desktop profile.
---

File access policy (single-machine profile):

- **Local read/write is unrestricted.** You may read and write any
  path on the host filesystem.
- **Prefer the exact `session_attachments` path** as your first
  file-reading call when the user attached the file (and the
  attachment id when referenced by id).
- **OpenClaw / skill config:** To read API keys or settings for
  installed skills, use the `config_file` tool with
  `file_path: "~/.openclaw/openclaw.json"` (operation `read` or
  `query`). The file stores skill env vars under
  `skills.entries.<skill-name>.env`. Do NOT use code_execution to
  read this file — the `config_file` tool handles it directly.
- **No destructive sweeps outside the task scope.** Avoid mass deletes
  or `rm -rf` against directories the user did not explicitly point
  you at. When the task does call for deleting many files or
  rewriting git history, confirm intent first (see the `human_gate`
  policy).
- **Save only on request.** When the user wants an answer in chat,
  respond inline — do not write files unless they asked to save,
  export, persist, or download.
