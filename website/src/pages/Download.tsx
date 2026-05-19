import { Section } from "@/components/Section";
import { SectionHead } from "@/components/SectionHead";
import { Reveal } from "@/components/Reveal";
import { InstallCard } from "@/components/InstallCard";
import { Icon } from "@/components/Icon";
import { useI18n } from "@/i18n/I18nProvider";
import { RELEASES_URL } from "@/lib/content";

export default function Download() {
  const { t } = useI18n();

  return (
    <>
      {/* ── Lede ─────────────────────────────────────────────── */}
      <Section className="pt-32 pb-10">
        <div className="grid items-end gap-10 md:grid-cols-12 md:gap-x-12">
          <div className="md:col-span-7">
            <Reveal>
              <p className="eyebrow mb-6">{t.downloadPage.eyebrow}</p>
            </Reveal>
            <Reveal delay={80}>
              <h1 className="font-display text-3xl font-semibold leading-[1.08] tracking-tight text-text-primary md:text-5xl lg:text-6xl">
                {t.downloadPage.title}
              </h1>
            </Reveal>
          </div>
          <Reveal delay={140} className="md:col-span-5">
            <p className="text-base leading-relaxed text-text-secondary">
              {t.downloadPage.sub}
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <a
                href={RELEASES_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="glass group inline-flex items-center justify-center gap-2 rounded-full px-5 py-3 text-sm font-medium text-text-primary transition hover:-translate-y-0.5 hover:text-accent"
              >
                <Icon name="windows" className="h-4 w-4" />
                <span>{t.downloadPage.windowsButton}</span>
              </a>
              <a
                href={RELEASES_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="glass group inline-flex items-center justify-center gap-2 rounded-full px-5 py-3 text-sm font-medium text-text-primary transition hover:-translate-y-0.5 hover:text-accent"
              >
                <Icon name="macos" className="h-4 w-4" />
                <span>{t.downloadPage.macosButton}</span>
              </a>
            </div>
          </Reveal>
        </div>
      </Section>

      {/* ── Install ──────────────────────────────────────────── */}
      <Section className="pt-12 pb-24">
        <SectionHead
          eyebrow={t.about.installEyebrow}
          title={t.about.installTitle}
        />
        <InstallCard />
      </Section>
    </>
  );
}
