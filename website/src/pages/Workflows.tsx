import { Link } from "react-router-dom";
import { Section } from "@/components/Section";
import { SectionHead } from "@/components/SectionHead";
import { FeatureShot } from "@/components/FeatureShot";
import { ClaimGrid, Claim } from "@/components/ClaimGrid";
import { Reveal } from "@/components/Reveal";
import { Icon } from "@/components/Icon";
import { useI18n } from "@/i18n/I18nProvider";
import { FEATURE_IMAGE_BY_ID } from "@/lib/features";
import { REPO_URL } from "@/lib/content";

export default function Workflows() {
  const { t } = useI18n();
  const wf = t.workflows;

  const shots = wf.screenshots.map((shot) => ({
    ...shot,
    imageSrc: FEATURE_IMAGE_BY_ID[shot.id] ?? "/images/features/placeholder.png",
  }));

  const titleLines = wf.heroTitle.split("\n");

  return (
    <>
      {/* Hero */}
      <Section className="pt-32 pb-12">
        <div className="grid items-end gap-10 md:grid-cols-12 md:gap-x-12">
          <div className="md:col-span-8">
            <Reveal delay={60}>
              <p className="eyebrow mb-5">{wf.heroEyebrow}</p>
            </Reveal>
            <Reveal delay={100}>
              <h1 className="font-display text-4xl font-semibold leading-[1.06] tracking-tight text-text-primary md:text-6xl lg:text-[4.25rem]">
                {titleLines.map((line, i) => (
                  <span key={line} className={i === titleLines.length - 1 ? "text-accent" : undefined}>
                    {line}
                    {i < titleLines.length - 1 && <br />}
                  </span>
                ))}
              </h1>
            </Reveal>
          </div>

          <Reveal delay={160} className="md:col-span-4">
            <p className="text-base leading-relaxed text-text-secondary">
              {wf.heroSub}
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
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
                {t.common.viewSource}
              </a>
            </div>
            <p className="mt-5 font-mono text-[11px] tracking-[0.12em] text-text-muted">
              {wf.heroMeta}
            </p>
          </Reveal>
        </div>

        <Reveal delay={220}>
          <div className="hero-canvas mt-16">
            <div className="hero-canvas__inner">
              <img
                src={FEATURE_IMAGE_BY_ID.workflowEditor}
                alt={wf.heroEyebrow}
                className="hero-canvas__image"
              />
            </div>
          </div>
        </Reveal>
      </Section>

      {/* Feature screenshots */}
      <Section className="pt-16 pb-20 md:pt-24">
        <SectionHead
          eyebrow={wf.featuresEyebrow}
          title={wf.featuresTitle}
          lede={wf.featuresSub}
        />
        <div className="feature-shot-grid">
          {shots.map((item, index) => (
            <Reveal key={item.id} delay={index * 60}>
              <FeatureShot
                item={item}
                index={index}
                placeholderNote={t.intro.placeholderNote}
              />
            </Reveal>
          ))}
        </div>
      </Section>

      {/* Three shapes, one engine */}
      <Section className="pt-0 pb-20">
        <SectionHead
          eyebrow={wf.shapesEyebrow}
          title={wf.shapesTitle}
          lede={wf.shapesSub}
        />
        <ClaimGrid columns={3}>
          {wf.shapes.map((shape) => (
            <Claim key={shape.title} label={shape.tag} title={shape.title}>
              {shape.description}
            </Claim>
          ))}
        </ClaimGrid>
      </Section>

      {/* Engineering claims */}
      <Section className="pt-0 pb-20">
        <SectionHead eyebrow={wf.claimsEyebrow} title={wf.claimsTitle} />
        <ClaimGrid columns={2}>
          {wf.claims.map((claim) => (
            <Claim key={claim.title} title={claim.title}>
              {claim.description}
            </Claim>
          ))}
        </ClaimGrid>
      </Section>

      {/* CTA */}
      <Section className="pt-0 pb-28">
        <Reveal>
          <div className="cta-band">
            <h2 className="font-display text-2xl font-semibold tracking-tight text-text-primary md:text-3xl">
              {wf.ctaTitle}
            </h2>
            <p className="mt-3 max-w-2xl text-base leading-relaxed text-text-secondary">
              {wf.ctaSub}
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
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
                {t.common.viewSource}
              </a>
            </div>
          </div>
        </Reveal>
      </Section>
    </>
  );
}
