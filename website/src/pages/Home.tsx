import { Link } from "react-router-dom";
import { Section } from "@/components/Section";
import { SectionHead } from "@/components/SectionHead";
import { ClaimGrid, Claim } from "@/components/ClaimGrid";
import { Reveal } from "@/components/Reveal";
import { Icon } from "@/components/Icon";
import { useI18n } from "@/i18n/I18nProvider";
import { REPO_URL } from "@/lib/content";

export default function Home() {
  const { t } = useI18n();

  return (
    <>
      {/* ── Hero ─────────────────────────────────────────────── */}
      <Section className="pt-32 pb-12">
        <div className="grid items-end gap-10 md:grid-cols-12 md:gap-x-12">
          <div className="md:col-span-8">
            <Reveal>
              <p className="eyebrow mb-6">{t.home.kicker}</p>
            </Reveal>
            <Reveal delay={80}>
              <h1 className="font-display text-4xl font-semibold leading-[1.04] tracking-tight text-text-primary md:text-6xl lg:text-7xl">
                {t.home.heroLine1}
                <br />
                <span className="text-accent">{t.home.heroLine2}</span>
                <br />
                {t.home.heroLine3}
              </h1>
            </Reveal>
          </div>

          <Reveal delay={140} className="md:col-span-4">
            <p className="text-base leading-relaxed text-text-secondary">
              {t.home.heroSub}
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Link to="/download" className="btn btn-primary">
                {t.common.download}
                <Icon name="arrow" className="h-4 w-4" />
              </Link>
              <a
                href={REPO_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-ghost"
              >
                <Icon name="github" className="h-4 w-4" />
                {t.common.viewOnGithub}
              </a>
            </div>
            <p className="mt-5 font-mono text-[11px] tracking-[0.12em] text-text-muted">
              {t.home.heroMeta}
            </p>
          </Reveal>
        </div>

        <Reveal delay={220}>
          <div className="hero-canvas mt-16">
            <div className="hero-canvas__inner">
              <img
                src="/images/previews/home-preview.png"
                alt="LeAgent desktop preview"
                className="h-full w-full object-cover"
              />
            </div>
          </div>
        </Reveal>
      </Section>

      {/* ── Foundations ──────────────────────────────────────── */}
      <Section id="intro" className="pt-20 pb-24 md:pt-28 md:pb-32">
        <SectionHead
          eyebrow={t.home.principlesEyebrow}
          title={t.home.principlesTitle}
          lede={t.home.introP1}
        />
        <ClaimGrid columns={3}>
          {t.principles.slice(0, 3).map((p) => (
            <Claim key={p.title} title={p.title}>
              {p.short}
            </Claim>
          ))}
        </ClaimGrid>
      </Section>

      {/* ── Continue reading ─────────────────────────────────── */}
      <Section className="pt-0 pb-24">
        <div className="grid items-baseline gap-x-12 gap-y-8 md:grid-cols-12">
          <div className="md:col-span-7">
            <h2 className="font-display text-2xl font-semibold tracking-tight text-text-primary md:text-3xl">
              {t.home.businessTitle}
            </h2>
          </div>

          <nav
            className="md:col-span-5 md:pt-2"
            aria-label="Continue reading"
          >
            <ul>
              {[
                {
                  to: "/about",
                  label: t.common.learnMore,
                  meta: "about",
                },
                {
                  to: "/business",
                  label: t.common.exploreUseCases,
                  meta: "business",
                },
                {
                  to: "/download",
                  label: t.common.download,
                  meta: "download",
                },
              ].map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    className="group flex items-baseline justify-between gap-4 py-3.5 transition-colors"
                  >
                    <span className="font-display text-sm font-medium text-text-secondary group-hover:text-accent">
                      {item.label}
                    </span>
                    <span className="font-mono text-[11px] uppercase tracking-[0.15em] text-text-muted group-hover:text-text-secondary">
                      → {item.meta}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </Section>
    </>
  );
}
