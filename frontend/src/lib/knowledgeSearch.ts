/**
 * Knowledge-base search interaction policy.
 *
 * Goals:
 * - Avoid firing expensive chunk BM25 on every keystroke / single Latin letter
 * - Keep typing responsive (commit only after debounce + gate)
 * - Allow Enter to force an intentional short query
 */

/** Debounce before auto-committing a remote content search. */
export const KNOWLEDGE_SEARCH_DEBOUNCE_MS = 450;

/** Soft cap for UI result volume (faster round-trips than 100). */
export const KNOWLEDGE_SEARCH_LIMIT = 30;

const CJK_OR_KANA_OR_HANGUL =
  /[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]/;

export function normalizeKnowledgeQuery(raw: string): string {
  return raw.trim().replace(/\s+/g, ' ');
}

/**
 * Whether debounced auto-search should hit the content index.
 * - Empty → no
 * - ≥2 Unicode code points → yes
 * - Single CJK/kana/hangul → yes (meaningful token)
 * - Single Latin letter / digit / punctuation → no
 */
export function shouldAutoSearch(query: string): boolean {
  const q = normalizeKnowledgeQuery(query);
  if (!q) return false;
  const chars = Array.from(q);
  if (chars.length >= 2) return true;
  return CJK_OR_KANA_OR_HANGUL.test(chars[0]!);
}

/** Enter / explicit submit: any non-empty normalized query. */
export function shouldForceSearch(query: string): boolean {
  return normalizeKnowledgeQuery(query).length > 0;
}

/**
 * Resolve the committed remote query from a draft.
 * Returns '' when search mode should not be active.
 */
export function commitKnowledgeSearchQuery(
  draft: string,
  opts: { force?: boolean } = {},
): string {
  const q = normalizeKnowledgeQuery(draft);
  if (!q) return '';
  if (opts.force ? shouldForceSearch(q) : shouldAutoSearch(q)) {
    return q;
  }
  return '';
}
