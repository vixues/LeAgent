import { Link } from "react-router-dom";
import { Section } from "@/components/Section";
import { SectionHead } from "@/components/SectionHead";
import { ClaimGrid, Claim } from "@/components/ClaimGrid";
import { Reveal } from "@/components/Reveal";
import { Icon } from "@/components/Icon";
import { useI18n } from "@/i18n/I18nProvider";
import { REPO_URL } from "@/lib/content";

export default function Home() {
  const { t, lang } = useI18n();
  const homePreviewSrc =
    lang === "en-US"
      ? "/images/previews/home-preview-en.png"
      : "/images/previews/home-preview.png";

  return (
    <>
      <Section className="pt-32 pb-12">
        <div className="grid items-start gap-10 md:grid-cols-12 md:gap-x-12">
          <div className="md:col-span-8">
            <Reveal delay={80}>
              <h1 className="font-display text-4xl font-semibold leading-[1.04] tracking-tight text-text-primary md:text-6xl lg:text-7xl">
                {t.home.heroLine1}
                <br />
                <span className="text-accent">{t.home.heroLine2}</span>
              </h1>
            </Reveal>
          </div>

          <Reveal delay={140} className="md:col-span-4">
            <div className="hero-aside ml-auto flex w-full max-w-md flex-col items-end gap-5 text-right">
              <p className="w-full text-right text-base leading-[1.65] text-text-secondary">
                {t.home.heroSub}
              </p>
              <div className="flex flex-wrap items-center justify-end gap-2.5">
                <Link to="/download" className="btn btn-primary">
                  <Icon name="download" className="h-4 w-4" />
                  {t.common.download}
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
            </div>
          </Reveal>
        </div>

        <Reveal delay={220}>
          <div className="hero-canvas mt-16">
            <div className="hero-canvas__inner">
              <img
                src={homePreviewSrc}
                alt="LeAgent workspace"
                className="hero-canvas__image"
              />
            </div>
          </div>
        </Reveal>
      </Section>

      <Section className="pt-20 pb-28 md:pt-28 md:pb-32">
        <SectionHead
          title={t.home.overviewTitle}
          lede={t.home.overviewLede}
        />
        <ClaimGrid columns={3}>
          {t.principles.slice(0, 3).map((p) => (
            <Claim key={p.title} title={p.title}>
              {p.short}
            </Claim>
          ))}
        </ClaimGrid>
      </Section>

      <Section className="pt-0 pb-28 md:pb-32">
        <SectionHead title={t.home.principlesTitle} />
        <ClaimGrid columns={3}>
          {t.principles.slice(3).map((p) => (
            <Claim key={p.title} title={p.title}>
              {p.short}
            </Claim>
          ))}
        </ClaimGrid>
      </Section>
    </>
  );
}
