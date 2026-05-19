import { Section } from "@/components/Section";
import { SectionHead } from "@/components/SectionHead";
import { ClaimGrid, Claim } from "@/components/ClaimGrid";
import { Reveal } from "@/components/Reveal";
import { InstallCard } from "@/components/InstallCard";
import { useI18n } from "@/i18n/I18nProvider";
import { README_URL } from "@/lib/content";

export default function About() {
  const { t } = useI18n();

  return (
    <>
      {/* ── Manifesto ────────────────────────────────────────── */}
      <Section className="pt-32 pb-12">
        <div className="grid items-end gap-10 md:grid-cols-12 md:gap-x-12">
          <div className="md:col-span-7">
            <Reveal>
              <p className="eyebrow mb-6">{t.about.eyebrow}</p>
            </Reveal>
            <Reveal delay={80}>
              <h1 className="font-display text-3xl font-semibold leading-[1.08] tracking-tight whitespace-pre-line text-text-primary md:text-5xl lg:text-6xl">
                {t.about.title}
              </h1>
            </Reveal>
          </div>

          <Reveal delay={140} className="md:col-span-5">
            <p className="text-base leading-relaxed text-text-secondary">
              {t.about.p1}
            </p>
            <div className="mt-6 border-l border-border pl-4 font-mono text-sm text-text-muted">
              <p>{t.about.quote}</p>
              <p className="mt-1 text-text-muted/70">{t.about.quoteSub}</p>
            </div>
          </Reveal>
        </div>

        <Reveal delay={220}>
          <div className="hero-canvas mt-16">
            <div className="hero-canvas__inner">
              <img
                src="/images/previews/about-preview.png"
                alt="LeAgent workspace interface"
                className="h-full w-full object-cover"
              />
            </div>
          </div>
        </Reveal>
      </Section>

      {/* ── Principles ───────────────────────────────────────── */}
      <Section className="pt-20 pb-24 md:pt-28 md:pb-32">
        <SectionHead
          eyebrow={t.about.principlesEyebrow}
          title={t.about.principlesTitle}
        />
        <ClaimGrid columns={3}>
          {t.principles.map((p) => (
            <Claim key={p.title} title={p.title}>
              {p.short}
            </Claim>
          ))}
        </ClaimGrid>
      </Section>

      {/* ── Install ──────────────────────────────────────────── */}
      <Section id="install" className="pt-0 pb-24">
        <SectionHead
          eyebrow={t.about.installEyebrow}
          title={t.about.installTitle}
        />
        <InstallCard
          footer={
            <>
              {t.about.installFooter}{" "}
              <a
                href={README_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent/80 transition-colors hover:text-accent"
              >
                {t.about.readmeLink}
              </a>
              .
            </>
          }
          showResourceLinks={false}
        />
      </Section>
    </>
  );
}
