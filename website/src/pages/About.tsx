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
        <SectionHead title={t.intro.title} lede={t.intro.sub} />
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
    </>
  );
}
