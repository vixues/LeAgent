import { Section } from "@/components/Section";
import { SectionHead } from "@/components/SectionHead";
import { FeatureShot } from "@/components/FeatureShot";
import { Reveal } from "@/components/Reveal";
import { useI18n } from "@/i18n/I18nProvider";
import { FEATURE_IMAGE_BY_ID } from "@/lib/features";

export default function About() {
  const { t } = useI18n();

  const shots = t.intro.screenshots.map((shot) => ({
    ...shot,
    imageSrc: FEATURE_IMAGE_BY_ID[shot.id] ?? "/images/features/placeholder.png",
  }));

  return (
    <>
      <Section className="pt-32 pb-12">
        <SectionHead
          eyebrow={t.intro.featuresEyebrow}
          title={t.intro.title}
          lede={t.intro.sub}
        />
      </Section>

      <Section className="pt-0 pb-24">
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

      <Section className="pt-0 pb-28">
        <SectionHead
          eyebrow={t.intro.multiModel.eyebrow}
          title={t.intro.multiModel.title}
          lede={t.intro.multiModel.sub}
        />
        <div className="provider-grid">
          {t.intro.multiModel.providers.map((p, index) => (
            <Reveal key={p.name} delay={index * 40}>
              <div className="provider-card">
                <p className="provider-card__name">{p.name}</p>
                <p className="provider-card__note">{p.note}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </Section>
    </>
  );
}
