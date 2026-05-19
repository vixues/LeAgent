/**
 * Build a single-line @skill token for chat (resolved by manifest ``name``).
 * Label is human-readable; skillName is the kebab-case skill id.
 */
export function buildSkillChatToken(displayName: string, skillName: string): string {
  const id = skillName.trim().replace(/[\s@#]/g, '').replace(/_/g, '-');
  if (!id) {
    return '@skill:skill#invalid';
  }
  const trimmed = displayName.trim() || id;
  const safe =
    trimmed.replace(/[@#\r\n]/g, '_').replace(/\s+/g, '_').trim() || id;
  return `@skill:${safe}#${id}`;
}
