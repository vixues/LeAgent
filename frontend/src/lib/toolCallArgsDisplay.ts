import type { TFunction } from 'i18next';

/** Above this length, `__raw__` is replaced in UI so megabyte tool JSON does not flood the chat. */
export const TOOL_CALL_RAW_REDACT_THRESHOLD = 2000;

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

/**
 * When the model failed to emit valid JSON, the backend keeps the string as `__raw__`.
 * That string can be huge; omit it in **display** only so the panel stays readable.
 */
export function redactLargeRawToolArguments(args: unknown, _t: TFunction): unknown {
  if (!isPlainObject(args)) return args;
  const raw = args.__raw__;
  if (typeof raw !== 'string' || raw.length <= TOOL_CALL_RAW_REDACT_THRESHOLD) return args;
  const { __raw__, ...rest } = args;
  return Object.keys(rest).length > 0 ? rest : undefined;
}
