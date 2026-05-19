export type ComposerTriggerKind = '/' | '@';

export interface ComposerTriggerMatch {
  kind: ComposerTriggerKind;
  query: string;
  /** Length of trigger + query at end of `before` (caret-relative removal). */
  tokenLength: number;
}

/**
 * Active ``/`` or ``@`` token immediately before the caret.
 * Does not require whitespace before the trigger (CJK text like ``介绍@`` works).
 */
export function matchComposerTriggerToken(
  before: string,
): ComposerTriggerMatch | null {
  const m = /([/@])(\S*)$/.exec(before);
  if (!m || (m[1] !== '/' && m[1] !== '@')) return null;
  const query = m[2] ?? '';
  return {
    kind: m[1] as ComposerTriggerKind,
    query,
    tokenLength: m[1].length + query.length,
  };
}
