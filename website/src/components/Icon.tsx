import { cn } from "@/lib/cn";

export type IconName =
  | "noAccount"
  | "noTracking"
  | "openSource"
  | "extensible"
  | "localData"
  | "developer"
  | "privacy"
  | "linux"
  | "macos"
  | "windows"
  | "shield"
  | "circle"
  | "arrow"
  | "external"
  | "mail"
  | "globe"
  | "github"
  | "twitter"
  | "heart"
  | "chat"
  | "bell"
  | "palette"
  | "sun"
  | "moon"
  | "download"
  | "sparkle";

interface IconProps {
  name: IconName;
  className?: string;
  strokeWidth?: number;
}

/**
 * Calligraphic single-stroke icons.
 * Stroke-based, balanced negative space, designed to sit inside `.icon-tile`.
 * Inspired by I Ching aesthetics: one stroke, no decoration, line equals form.
 */
export function Icon({ name, className, strokeWidth = 1.5 }: IconProps) {
  const common = {
    viewBox: "0 0 24 24",
    fill: "none" as const,
    stroke: "currentColor",
    strokeWidth,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    className: cn("h-5 w-5", className),
  };

  switch (name) {
    case "noAccount":
      return (
        <svg {...common}>
          <circle cx="12" cy="9" r="3.5" />
          <path d="M5.5 19c.6-3.4 3.2-5.5 6.5-5.5s5.9 2.1 6.5 5.5" />
          <path d="m4.5 4.5 15 15" opacity="0.55" />
        </svg>
      );
    case "noTracking":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="3" />
          <path d="M2.5 12C4.8 7.5 8.2 5 12 5s7.2 2.5 9.5 7c-2.3 4.5-5.7 7-9.5 7s-7.2-2.5-9.5-7Z" />
          <path d="m4 4 16 16" opacity="0.6" />
        </svg>
      );
    case "openSource":
      return (
        <svg {...common}>
          <path d="m9 17-5-5 5-5" />
          <path d="m15 7 5 5-5 5" />
          <path d="m14 6-4 12" opacity="0.7" />
        </svg>
      );
    case "extensible":
      return (
        <svg {...common}>
          <rect x="3" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="3" width="7" height="7" rx="1.5" />
          <rect x="8.5" y="14" width="7" height="7" rx="1.5" />
          <path d="M10 6.5h4M12 10v4" opacity="0.7" />
        </svg>
      );
    case "localData":
      return (
        <svg {...common}>
          <ellipse cx="12" cy="7" rx="7" ry="2.5" />
          <path d="M5 7v10c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5V7" />
          <path d="M5 12c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5" opacity="0.55" />
        </svg>
      );
    case "developer":
      return (
        <svg {...common}>
          <path d="M4 6h16" />
          <path d="M4 12h10" />
          <path d="M4 18h13" />
          <path d="m18 9 3 3-3 3" />
        </svg>
      );
    case "privacy":
      return (
        <svg {...common}>
          <path d="M12 3 5 6v6c0 4 3 7.5 7 9 4-1.5 7-5 7-9V6l-7-3Z" />
          <path d="M9.5 12.5 11 14l3.5-3.5" />
        </svg>
      );
    case "linux":
      return (
        <svg {...common}>
          <rect x="3.5" y="4.5" width="17" height="12" rx="1.5" />
          <path d="M8 20h8" />
          <path d="M12 16.5V20" />
        </svg>
      );
    case "macos":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      );
    case "windows":
      return (
        <svg {...common}>
          <path d="M3.5 5.5 11 4.5v7.5H3.5z" />
          <path d="M13 4.2 20.5 3v9.5H13z" />
          <path d="M3.5 12.5H11V19.5L3.5 18.5z" />
          <path d="M13 13.5H20.5V21L13 19.8z" />
        </svg>
      );
    case "shield":
      return (
        <svg {...common}>
          <path d="M12 3 5 6v6c0 4 3 7.5 7 9 4-1.5 7-5 7-9V6l-7-3Z" />
        </svg>
      );
    case "circle":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" />
        </svg>
      );
    case "arrow":
      return (
        <svg {...common}>
          <path d="M5 12h14" />
          <path d="m13 6 6 6-6 6" />
        </svg>
      );
    case "external":
      return (
        <svg {...common}>
          <path d="M7 17 17 7" />
          <path d="M9 7h8v8" />
        </svg>
      );
    case "mail":
      return (
        <svg {...common}>
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <path d="m4 7 8 6 8-6" />
        </svg>
      );
    case "globe":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18" />
          <path d="M12 3a14 14 0 0 1 4 9 14 14 0 0 1-4 9 14 14 0 0 1-4-9 14 14 0 0 1 4-9Z" />
        </svg>
      );
    case "github":
      return (
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={cn("h-5 w-5", className)}>
          <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2Z" />
        </svg>
      );
    case "twitter":
      return (
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={cn("h-5 w-5", className)}>
          <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
        </svg>
      );
    case "heart":
      return (
        <svg {...common}>
          <path d="M12 20s-7-4.5-9-9.5C1.5 7 4 4 7 4c1.8 0 3.5 1 5 2.5C13.5 5 15.2 4 17 4c3 0 5.5 3 4 6.5-2 5-9 9.5-9 9.5Z" />
        </svg>
      );
    case "chat":
      return (
        <svg {...common}>
          <path d="M4 5h16v11H8l-4 4V5Z" />
          <path d="M8 9.5h8" />
          <path d="M8 12.5h5" />
        </svg>
      );
    case "bell":
      return (
        <svg {...common}>
          <path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2H4.5Z" />
          <path d="M10.5 20a1.5 1.5 0 0 0 3 0" />
        </svg>
      );
    case "palette":
      return (
        <svg {...common}>
          <path d="M12 3a9 9 0 0 0 0 18 2 2 0 0 0 2-2c0-1.1.9-2 2-2h1a4 4 0 0 0 4-4 9 9 0 0 0-9-10Z" />
          <circle cx="7.5" cy="11" r="1" fill="currentColor" />
          <circle cx="11" cy="7.5" r="1" fill="currentColor" />
          <circle cx="15.5" cy="9" r="1" fill="currentColor" />
        </svg>
      );
    case "sun":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4" />
        </svg>
      );
    case "moon":
      return (
        <svg {...common}>
          <path d="M20.5 14.5A8 8 0 0 1 9.5 3.5a8 8 0 1 0 11 11Z" />
        </svg>
      );
    case "download":
      return (
        <svg {...common}>
          <path d="M12 4v11" />
          <path d="m7 11 5 5 5-5" />
          <path d="M5 20h14" />
        </svg>
      );
    case "sparkle":
      return (
        <svg {...common}>
          <path d="M12 3v6M12 15v6M3 12h6M15 12h6" />
          <path d="m6 6 3 3M15 15l3 3M6 18l3-3M15 9l3-3" opacity="0.6" />
        </svg>
      );
  }
}
