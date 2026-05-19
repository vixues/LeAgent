/** Parse GitHub repo URLs for the skills hub catalog (directory of skill folders). */

export interface ParsedGitHubSkillsRepo {
  owner: string;
  repo: string;
  ref: string;
  skillsPath: string;
}

/**
 * Supports:
 * - `https://github.com/owner/repo`
 * - `https://github.com/owner/repo/tree/main/skills` (optional ref + subtree)
 */
export function parseGitHubSkillsRepoUrl(input: string): ParsedGitHubSkillsRepo | null {
  const raw = input.trim();
  if (!raw) {
    return null;
  }
  try {
    const u = new URL(raw.includes('://') ? raw : `https://${raw}`);
    const host = u.hostname.toLowerCase();
    if (host !== 'github.com' && !host.endsWith('.github.com')) {
      return null;
    }
    const parts = u.pathname.split('/').filter(Boolean);
    if (parts.length < 2) {
      return null;
    }
    const owner = parts[0];
    const repoRaw = parts[1];
    if (!owner || !repoRaw) {
      return null;
    }
    const repo = repoRaw.replace(/\.git$/, '');
    let ref = 'main';
    let skillsPath = 'skills';
    if (parts[2] === 'tree' && parts.length >= 4) {
      ref = parts[3] ?? 'main';
      if (parts.length > 4) {
        skillsPath = parts.slice(4).join('/') || 'skills';
      }
    }
    return { owner, repo, ref, skillsPath };
  } catch {
    return null;
  }
}
