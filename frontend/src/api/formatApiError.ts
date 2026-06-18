/** Format FastAPI ``detail`` payloads into user-visible error strings. */
export function formatHttpErrorDetail(detail: unknown, status: number, fallbackMessage?: string): string {
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const parts = detail.map((e) => {
      if (e && typeof e === 'object' && 'msg' in e) {
        return String((e as { msg?: string }).msg ?? e);
      }
      return String(e);
    });
    if (parts.length) return parts.join('; ');
  }
  if (detail && typeof detail === 'object') {
    const record = detail as Record<string, unknown>;
    const validation = record.validation_errors;
    if (validation && typeof validation === 'object' && !Array.isArray(validation)) {
      const lines: string[] = [];
      for (const [nodeId, errs] of Object.entries(validation as Record<string, unknown[]>)) {
        if (!Array.isArray(errs)) continue;
        for (const err of errs) {
          if (err && typeof err === 'object' && 'message' in err) {
            lines.push(`${nodeId}: ${String((err as { message: string }).message)}`);
          }
        }
      }
      if (lines.length) return lines.join('\n');
    }
  }
  return fallbackMessage || `HTTP ${status}`;
}
