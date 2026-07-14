import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useI18n } from "@/i18n/I18nProvider";
import { cn } from "@/lib/cn";
import {
  TUTORIAL_SECTIONS,
  articlePath,
  type TutorialSectionId,
} from "@/lib/tutorials";

function DocsSidebar({
  onNavigate,
}: {
  onNavigate?: () => void;
}) {
  const { lang, t } = useI18n();
  const { pathname } = useLocation();

  return (
    <nav className="docs-sidebar" aria-label={t.tutorials.tocLabel}>
      <Link
        to="/tutorials"
        onClick={onNavigate}
        className={cn(
          "docs-sidebar__hub",
          pathname === "/tutorials" && "docs-sidebar__hub--active",
        )}
      >
        {t.tutorials.hubLink}
      </Link>

      {TUTORIAL_SECTIONS.map((section) => (
        <div key={section.id} className="docs-sidebar__group">
          <div className="docs-sidebar__group-title">
            {section.title[lang]}
          </div>
          <ul className="docs-sidebar__list">
            {section.articles.map((article) => {
              const to = articlePath(section.id, article.slug);
              return (
                <li key={article.slug}>
                  <NavLink
                    to={to}
                    end={section.id === "intro" || article.slug === "index"}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        "docs-sidebar__link",
                        isActive && "docs-sidebar__link--active",
                      )
                    }
                  >
                    {article.title[lang]}
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export default function TutorialsLayout() {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);

  return (
    <div className="docs-shell">
      <div className="docs-shell__inner">
        <aside className="docs-shell__aside hidden lg:block">
          <div className="docs-shell__aside-sticky">
            <DocsSidebar />
          </div>
        </aside>

        <div className="docs-shell__main">
          <div className="mb-6 lg:hidden">
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
            >
              {open ? t.tutorials.closeToc : t.tutorials.openToc}
            </button>
            {open && (
              <div className="mt-3 max-h-[60vh] overflow-y-auto rounded-lg border border-border-subtle bg-surface/60 p-4">
                <DocsSidebar onNavigate={() => setOpen(false)} />
              </div>
            )}
          </div>
          <Outlet />
        </div>
      </div>
    </div>
  );
}

export type { TutorialSectionId };
