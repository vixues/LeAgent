import { Section } from "@/components/Section";
import { SectionHead } from "@/components/SectionHead";
import { ClaimGrid, Claim } from "@/components/ClaimGrid";
import { Reveal } from "@/components/Reveal";
import { Icon } from "@/components/Icon";
import { useI18n } from "@/i18n/I18nProvider";
import { Link } from "react-router-dom";

export default function Business() {
  const { t } = useI18n();

  return (
    <>
      <Section className="pt-32 pb-12">
        <div className="grid items-end gap-10 md:grid-cols-12 md:gap-x-12">
          <div className="md:col-span-7">
            <Reveal delay={80}>
              <h1 className="font-display text-3xl font-semibold leading-[1.08] tracking-tight whitespace-pre-line text-text-primary md:text-5xl lg:text-6xl">
                {t.business.title}
              </h1>
            </Reveal>
          </div>
          <Reveal delay={140} className="md:col-span-5">
            <p className="text-base leading-relaxed text-text-secondary">
              {t.business.sub}
            </p>
          </Reveal>
        </div>

        <Reveal delay={220}>
          <div className="hero-canvas mt-16">
            <div className="hero-canvas__inner">
              <img
                src="/images/previews/workflow-preview.png"
                alt="LeAgent workflow"
                className="h-full w-full object-cover"
              />
            </div>
          </div>
        </Reveal>
      </Section>

      <Section className="pt-20 pb-24 md:pt-28 md:pb-28">
        <SectionHead
          eyebrow={t.business.useCasesEyebrow}
          title={t.business.useCasesTitle}
        />
        <ClaimGrid columns={3}>
          {t.useCases.map((uc) => (
            <Claim key={uc.title} title={uc.title}>
              {uc.description}
            </Claim>
          ))}
        </ClaimGrid>
      </Section>

      <Section className="pt-0 pb-24">
        <SectionHead
          eyebrow={t.business.capabilitiesEyebrow}
          title={t.business.capabilitiesTitle}
        />
        <ClaimGrid columns={3}>
          {t.capabilities.map((cap) => (
            <Claim key={cap.title} title={cap.title}>
              {cap.description}
            </Claim>
          ))}
        </ClaimGrid>

        <div className="mt-16 flex flex-wrap items-baseline justify-between gap-x-12 gap-y-4">
          <div>
            <p className="font-display text-lg font-medium text-text-primary md:text-xl">
              {t.business.ctaTitle}
            </p>
            <p className="mt-2 max-w-xl text-sm leading-relaxed text-text-secondary">
              {t.business.ctaSub}
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link to="/company" className="btn btn-primary">
              {t.common.contactCustom}
              <Icon name="arrow" className="h-4 w-4" />
            </Link>
            <Link to="/download" className="btn btn-ghost">
              {t.common.startBuilding}
            </Link>
          </div>
        </div>
      </Section>
    </>
  );
}
