import { Section } from "@/components/Section";
import { Reveal } from "@/components/Reveal";
import { Icon, type IconName } from "@/components/Icon";
import { useI18n } from "@/i18n/I18nProvider";
import { CONTACT } from "@/lib/content";

interface ContactLink {
  labelKey: "email" | "github" | "xiaohongshu" | "website";
  value: string;
  href: string;
  icon: IconName;
  external?: boolean;
}

const LINKS: ContactLink[] = [
  {
    labelKey: "email",
    value: CONTACT.email,
    href: `mailto:${CONTACT.email}`,
    icon: "mail",
  },
  {
    labelKey: "github",
    value: CONTACT.github,
    href: `https://${CONTACT.github}`,
    icon: "github",
    external: true,
  },
  {
    labelKey: "xiaohongshu",
    value: CONTACT.xiaohongshu,
    href: CONTACT.xiaohongshuUrl,
    icon: "xiaohongshu",
    external: true,
  },
  {
    labelKey: "website",
    value: "LeAgent",
    href: "/#/",
    icon: "globe",
  },
];

export default function Company() {
  const { t } = useI18n();

  return (
    <Section className="flex min-h-[75vh] items-center pt-32">
      <div className="grid w-full items-end gap-12 md:grid-cols-12 md:gap-x-12">
        <div className="md:col-span-5">
          <Reveal>
            <p className="eyebrow mb-6">{t.company.eyebrow}</p>
          </Reveal>
          <Reveal delay={80}>
            <h1 className="font-display text-4xl font-semibold leading-[1.05] tracking-tight text-text-primary md:text-5xl">
              {CONTACT.name}
            </h1>
          </Reveal>
          <Reveal delay={140}>
            <div className="mt-10 border-l border-border pl-4 font-mono text-sm">
              <p className="text-text-secondary">{t.company.tao}</p>
              <p className="mt-1 text-text-muted/70 italic">
                {t.company.taoSub}
              </p>
            </div>
          </Reveal>
        </div>

        <Reveal delay={180} className="md:col-span-7">
          <ul>
            {LINKS.map((link) => (
              <li key={link.labelKey}>
                <a
                  href={link.href}
                  target={link.external ? "_blank" : undefined}
                  rel={link.external ? "noopener noreferrer" : undefined}
                  className="group grid grid-cols-12 items-center gap-x-6 py-4"
                >
                  <span className="col-span-4 inline-flex items-center gap-2.5 font-mono text-[11px] uppercase tracking-[0.15em] text-text-muted transition-colors group-hover:text-accent">
                    <Icon name={link.icon} className="h-4 w-4 shrink-0" />
                    {t.company.contactLabels[link.labelKey]}
                  </span>
                  <span className="col-span-7 font-mono text-sm text-text-secondary transition-colors group-hover:text-text-primary">
                    {link.value}
                  </span>
                  <span className="col-span-1 text-right text-text-muted opacity-0 transition-opacity group-hover:opacity-100">
                    <Icon name="external" className="ml-auto h-3.5 w-3.5" />
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </Reveal>
      </div>
    </Section>
  );
}
