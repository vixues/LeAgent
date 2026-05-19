# Human approval (`ask_user` permission UI)

Use this pattern when the user should **explicitly allow or deny** before you continue — for
example access to a sensitive path, running a high-impact tool, or switching to a different
model / reasoning mode.

1. **Call `ask_user` alone** in the turn (no other tool calls with it).
2. **Single question** for a yes/no style gate, with:
   - `"ui_variant": "permission"`
   - `"permission_kind"`: `file_access` | `tool_run` | `mode_change` | `generic`
   - `"detail"`: a short string the UI shows under the title (absolute path, tool name, or target mode name).
   - Optional: `"primary_choice"` / `"secondary_choice"` to override the default Allow / Deny button labels.
3. The client submits answer values **`allow`** or **`deny`**. If you set `"allow_custom": true`, the user
   may add a free-text note; treat the submitted string as their answer.
4. **After** you receive the tool result with their answers, proceed with ordinary tools in follow-up
   turns — and **respect a `deny`** (do not perform the blocked action; explain briefly and offer alternatives).

For multi-part clarification (not a simple gate), use the default questionnaire style: omit
`ui_variant` or set `"ui_variant": "questionnaire"`.
