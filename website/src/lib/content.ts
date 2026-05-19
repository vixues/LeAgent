const DEFAULT_REPO_URL = "https://github.com/vixues/LeAgent";
const DEFAULT_SITE_ORIGIN = "https://vixues.com.cn";

export const SITE_ORIGIN =
  import.meta.env.VITE_SITE_ORIGIN ?? DEFAULT_SITE_ORIGIN;

export const REPO_URL = import.meta.env.VITE_REPO_URL ?? DEFAULT_REPO_URL;

export const RELEASES_URL = `${REPO_URL}/releases`;
export const README_URL = `${REPO_URL}/blob/main/README.md`;
export const LICENSE_URL = `${REPO_URL}/blob/main/LICENSE`;
export const SECURITY_URL = `${REPO_URL}/blob/main/SECURITY.md`;

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
