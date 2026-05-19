import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/cn";
import { REPO_URL } from "@/lib/content";
import { useI18n } from "@/i18n/I18nProvider";
import { LanguageToggle } from "./LanguageToggle";
import { ThemeToggle } from "./ThemeToggle";

const faviconUrl = `${import.meta.env.BASE_URL}favicon.svg`;

export function SiteHeader() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const { t } = useI18n();

  const navItems = [
    { label: t.nav.about, to: "/" },
    { label: t.nav.intro, to: "/about" },
    { label: t.nav.business, to: "/business" },
    { label: t.nav.download, to: "/download" },
    { label: t.nav.pets, to: "/pets" },
    { label: t.nav.company, to: "/company" },
  ];

  return (
    <header className="fixed top-0 z-50 w-full glass-bar">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        {/* Brand */}
        <Link
          to="/"
          className="flex items-center gap-3 font-display text-lg font-semibold tracking-tight text-text-primary"
        >
          <img src={faviconUrl} width={36} height={36} alt="" />
          LeAgent
        </Link>

        {/* Desktop nav */}
        <nav className="hidden items-center gap-8 md:flex" aria-label="Main">
          {navItems.map((item) => {
            const active = pathname === item.to;
            return (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  "font-body text-sm transition-colors duration-200",
                  active
                    ? "text-accent"
                    : "text-text-secondary hover:text-text-primary",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Controls */}
        <div className="flex items-center gap-2">
          <LanguageToggle />
          <ThemeToggle />

          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="hidden text-text-secondary transition-colors hover:text-text-primary md:block"
            aria-label="GitHub"
          >
            <svg
              viewBox="0 0 24 24"
              fill="currentColor"
              className="h-5 w-5"
              aria-hidden="true"
            >
              <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2Z" />
            </svg>
          </a>

          <button
            type="button"
            onClick={() => setOpen(!open)}
            className="rounded p-1.5 text-text-muted transition-colors hover:text-text-primary md:hidden"
            aria-expanded={open}
            aria-label="Toggle menu"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              className="h-5 w-5"
            >
              {open ? (
                <path d="M6 6l12 12M6 18L18 6" />
              ) : (
                <path d="M4 8h16M4 16h16" />
              )}
            </svg>
          </button>
        </div>
      </div>

      {/* Mobile nav */}
      {open && (
        <nav
          className="border-t border-transparent glass px-6 py-4 md:hidden"
          aria-label="Mobile"
        >
          {navItems.map((item) => {
            return (
              <Link
                key={item.to}
                to={item.to}
                onClick={() => setOpen(false)}
                className="block py-2 text-sm text-text-secondary transition-colors hover:text-text-primary"
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      )}
    </header>
  );
}
