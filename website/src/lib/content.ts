const DEFAULT_REPO_URL = "https://github.com/vixues/LeAgent";
const DEFAULT_SITE_ORIGIN = "https://vixues.com.cn";

export const SITE_ORIGIN =
  import.meta.env.VITE_SITE_ORIGIN ?? DEFAULT_SITE_ORIGIN;

export const REPO_URL = import.meta.env.VITE_REPO_URL ?? DEFAULT_REPO_URL;

function parseGithubRepo(repoUrl: string): { owner: string; repo: string } {
  const match = repoUrl
    .replace(/\.git$/, "")
    .match(/github\.com[/:]([^/]+)\/([^/#?]+)/i);
  return {
    owner: match?.[1] ?? "vixues",
    repo: match?.[2] ?? "LeAgent",
  };
}

const { owner: GITHUB_OWNER, repo: GITHUB_REPO } = parseGithubRepo(REPO_URL);

/** Raw file base for README / docs assets on the public site. */
export const REPO_RAW_BASE = `https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/main`;

export const RELEASES_URL = `${REPO_URL}/releases`;
export const README_URL = `${REPO_URL}/blob/main/README.md`;
export const LICENSE_URL = `${REPO_URL}/blob/main/LICENSE`;
export const SECURITY_URL = `${REPO_URL}/blob/main/SECURITY.md`;

/** MIIT ICP filing (鄂ICP备2026023482号) */
export const ICP_BEIAN_URL = "https://beian.miit.gov.cn/";
export const ICP_BEIAN_NUMBER = "鄂ICP备2026023482号";

/** Public security bureau filing (粤公网安备44030002012706号) */
export const PSB_BEIAN_RECORD_CODE = "44030002012706";
export const PSB_BEIAN_URL = `https://www.beian.gov.cn/portal/registerSystemInfo?recordcode=${PSB_BEIAN_RECORD_CODE}`;
export const PSB_BEIAN_NUMBER = "粤公网安备44030002012706号";

export const INSTALL_SH_URL = `${SITE_ORIGIN}/install.sh`;
export const INSTALL_PS1_URL = `${SITE_ORIGIN}/install.ps1`;
export const INSTALL_BAT_URL = `${SITE_ORIGIN}/install.bat`;

export type OsKey = "linux" | "macos" | "windows";

export const CONTACT = {
  name: "Cheng Yuanqi",
  email: "vixues@gmail.com",
  github: "github.com/vixues",
  xiaohongshu: "@vixues",
  xiaohongshuUrl:
    "https://www.xiaohongshu.com/user/profile/5eb3f82e000000000100206e",
  website: "/",
} as const;
