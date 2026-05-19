import { useState, useCallback, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Icon, type IconName } from "@/components/Icon";
import { useI18n } from "@/i18n/I18nProvider";
import { REPO_URL, RELEASES_URL, type OsKey } from "@/lib/content";
import { cn } from "@/lib/cn";

const OS_TABS: { key: OsKey; icon: IconName }[] = [
  { key: "linux", icon: "linux" },
  { key: "macos", icon: "macos" },
  { key: "windows", icon: "windows" },
];

type InstallMode = "quick" | "source";

interface InstallCardProps {
  footer?: ReactNode;
  showResourceLinks?: boolean;
  showRequirements?: boolean;
}

export function InstallCard({
  footer,
  showResourceLinks = true,
  showRequirements = true,
}: InstallCardProps) {
  const [activeOs, setActiveOs] = useState<OsKey>("linux");
  const [installMode, setInstallMode] = useState<InstallMode>("quick");
  const [copied, setCopied] = useState(false);
  const { t } = useI18n();

  const current = t.install[activeOs];
  const activeCode =
    installMode === "quick" ? current.steps : current.fromSource;
  const activeTitle =
    installMode === "quick" ? t.common.quickInstall : t.common.fromSource;
  const activeLang = activeOs === "windows" ? "powershell" : "bash";
  const lines = activeCode.split("\n");

  const copy = useCallback(() => {
    navigator.clipboard.writeText(activeCode).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [activeCode]);

  return (
    <div className="workspace-install">
      <div className="workspace-install__header">
        <div className="workspace-install__heading">
          <Icon name="developer" className="h-3.5 w-3.5" />
          <span>Install workspace</span>
          <span className="workspace-install__badge">{current.label}</span>
        </div>

        <button
          type="button"
          onClick={copy}
          className="workspace-install__copy"
          aria-label="Copy install command"
        >
          {copied ? "copied" : "copy"}
        </button>
      </div>

      <div className="workspace-install__body">
        <aside className="workspace-install__rail">
          <p className="workspace-install__label">Platform</p>
          <div
            className="workspace-install__stack"
            role="tablist"
            aria-label="Platform"
          >
            {OS_TABS.map((os) => (
              <button
                key={os.key}
                type="button"
                role="tab"
                aria-selected={activeOs === os.key}
                onClick={() => setActiveOs(os.key)}
                className={cn(
                  "workspace-install__option",
                  activeOs === os.key && "workspace-install__option--active",
                )}
              >
                <Icon name={os.icon} className="h-3.5 w-3.5" />
                <span>{t.install[os.key].label}</span>
              </button>
            ))}
          </div>

          <p className="workspace-install__label mt-5">Method</p>
          <div
            className="workspace-install__stack"
            role="tablist"
            aria-label="Method"
          >
            {(
              [
                { key: "quick", label: t.common.quickInstall },
                { key: "source", label: t.common.fromSource },
              ] as const
            ).map((m) => (
              <button
                key={m.key}
                type="button"
                role="tab"
                aria-selected={installMode === m.key}
                onClick={() => setInstallMode(m.key)}
                className={cn(
                  "workspace-install__option",
                  installMode === m.key && "workspace-install__option--active",
                )}
              >
                <span>{m.label}</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="workspace-install__main" aria-label={activeTitle}>
          <div className="workspace-install__codebar">
            <div className="workspace-install__file">
              <span className="workspace-install__dot" />
              <span>{activeTitle}</span>
            </div>
            <span className="workspace-install__lang">{activeLang}</span>
          </div>

          <pre className="workspace-install__code">
            <code>
              <table>
                <tbody>
                  {lines.map((line, index) => (
                    <tr key={`${index}-${line}`}>
                      <td className="workspace-install__line">
                        {index + 1}
                      </td>
                      <td className="workspace-install__cmd">{line}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </code>
          </pre>
        </section>
      </div>

      <div className="workspace-install__footer">
        {showRequirements && (
          <ul className="workspace-install__reqs">
            {t.requirements.map((req) => (
              <li key={req}>{req}</li>
            ))}
          </ul>
        )}

        {showResourceLinks && (
          <div className="workspace-install__links">
            <a href={RELEASES_URL} target="_blank" rel="noopener noreferrer">
              <Icon name="github" className="h-3 w-3" />
              Releases
            </a>
            <Link to="/about#install">Docs</Link>
            <a href={REPO_URL} target="_blank" rel="noopener noreferrer">
              <Icon name="external" className="h-3 w-3" />
              Source
            </a>
          </div>
        )}

        {footer && <p className="workspace-install__note">{footer}</p>}
      </div>
    </div>
  );
}
