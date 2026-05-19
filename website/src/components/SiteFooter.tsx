import { Link } from "react-router-dom";
import { useI18n } from "@/i18n/I18nProvider";

const faviconUrl = `${import.meta.env.BASE_URL}favicon.svg`;

export function SiteFooter() {
  const { t } = useI18n();

  return (
    <footer className="glass border-t border-transparent">
      <div className="mx-auto max-w-6xl px-6 py-16">
        <div className="grid gap-12 md:grid-cols-4">
          {/* Brand column */}
          <div className="md:col-span-1">
            <Link
              to="/"
              className="mb-3 inline-flex items-center gap-2 font-display text-lg font-semibold text-text-primary"
            >
              <img src={faviconUrl} width={24} height={24} alt="" />
              LeAgent
            </Link>
            <p className="whitespace-pre-line text-sm leading-relaxed text-text-muted">
              {t.footer.tagline}
            </p>
          </div>

          {/* Pages */}
          <div>
            <h4 className="mb-4 font-display text-xs font-semibold uppercase tracking-widest text-text-muted">
              {t.footer.pages}
            </h4>
            <ul className="space-y-2 text-sm">
              {[
                { to: "/about", label: t.nav.about },
                { to: "/business", label: t.nav.business },
                { to: "/download", label: t.nav.download },
                { to: "/pets", label: t.nav.pets },
                { to: "/company", label: t.nav.company },
              ].map((link) => (
                <li key={link.to}>
                  <Link
                    to={link.to}
                    className="text-text-secondary transition-colors hover:text-text-primary"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Resources */}
          <div>
            <h4 className="mb-4 font-display text-xs font-semibold uppercase tracking-widest text-text-muted">
              {t.footer.resources}
            </h4>
            <ul className="space-y-2 text-sm">
              <li>
                <a
                  href="https://github.com/vixues/LeAgent"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-text-secondary transition-colors hover:text-text-primary"
                >
                  GitHub
                </a>
              </li>
              <li>
                <a
                  href="https://github.com/vixues/LeAgent/blob/main/README.md"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-text-secondary transition-colors hover:text-text-primary"
                >
                  {t.footer.documentation}
                </a>
              </li>
              <li>
                <a
                  href="https://github.com/vixues/LeAgent/releases"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-text-secondary transition-colors hover:text-text-primary"
                >
                  {t.footer.releases}
                </a>
              </li>
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h4 className="mb-4 font-display text-xs font-semibold uppercase tracking-widest text-text-muted">
              {t.footer.legal}
            </h4>
            <ul className="space-y-2 text-sm">
              <li>
                <a
                  href="https://github.com/vixues/LeAgent/blob/main/LICENSE"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-text-secondary transition-colors hover:text-text-primary"
                >
                  {t.footer.license}
                </a>
              </li>
              <li>
                <a
                  href="https://github.com/vixues/LeAgent/blob/main/SECURITY.md"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-text-secondary transition-colors hover:text-text-primary"
                >
                  {t.footer.security}
                </a>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="hairline mt-12" />
        <div className="mt-6 flex flex-col items-center justify-between gap-2 text-xs text-text-muted md:flex-row">
          <span>{t.footer.copyright}</span>
          <div className="text-center font-mono">
            <span className="opacity-60">{t.footer.tao}</span>
            <span className="mx-2 opacity-30">&middot;</span>
            <span className="opacity-40 italic">{t.footer.taoSub}</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
