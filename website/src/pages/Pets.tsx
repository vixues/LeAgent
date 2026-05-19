import { Section } from "@/components/Section";
import { SectionHead } from "@/components/SectionHead";
import { ClaimGrid, Claim } from "@/components/ClaimGrid";
import { Reveal } from "@/components/Reveal";
import { Icon } from "@/components/Icon";
import { useI18n } from "@/i18n/I18nProvider";

const WALLPAPER_IMAGES = [
  "/images/pets/wallpapers/xuan.png",
  "/images/pets/wallpapers/qing-shan.png",
  "/images/pets/wallpapers/vermillion.png",
  "/images/pets/wallpapers/raw-silk.png",
  "/images/pets/wallpapers/ink-mood.png",
  "/images/pets/wallpapers/cang.png",
];

const COMPANION_IMAGES = [
  "/images/pets/companions/cloud-child.png",
  "/images/pets/companions/ink-carp.png",
  "/images/pets/companions/paper-crane.png",
  "/images/pets/companions/mountain-sprite.png",
  "/images/pets/companions/lantern.png",
  "/images/pets/companions/tea-boy.png",
  "/images/pets/companions/bamboo-shadow.png",
  "/images/pets/companions/night-lamp.png",
];

export default function Pets() {
  const { t } = useI18n();

  return (
    <>
      {/* ── Hero + stage ─────────────────────────────────────── */}
      <Section className="pt-32 pb-12">
        <div className="grid items-end gap-10 md:grid-cols-12 md:gap-x-12">
          <div className="md:col-span-7">
            <Reveal>
              <p className="eyebrow mb-6">desktop pets</p>
            </Reveal>
            <Reveal delay={80}>
              <h1 className="font-display text-3xl font-semibold leading-[1.08] tracking-tight whitespace-pre-line text-text-primary md:text-5xl lg:text-6xl">
                {t.pets.title}
              </h1>
            </Reveal>
          </div>
          <Reveal delay={140} className="md:col-span-5">
            <p className="text-base leading-relaxed text-text-secondary">
              {t.pets.sub}
            </p>
          </Reveal>
        </div>

        <Reveal delay={220}>
          <div className="hero-canvas mt-16">
            <div className="hero-canvas__inner">
              <img
                src="/images/previews/pet-preview.png"
                alt="LeAgent desktop pet preview"
                className="hero-canvas__image"
              />
            </div>
          </div>
        </Reveal>
      </Section>

      {/* ── Behaviour ────────────────────────────────────────── */}
      <Section className="pt-20 pb-24">
        <SectionHead
          eyebrow={t.pets.featuresTitle}
          title={t.pets.introTitle}
          lede={t.pets.introP1}
        />
        <ClaimGrid columns={3}>
          {t.pets.features.map((f) => (
            <Claim key={f.title} title={f.title}>
              {f.description}
            </Claim>
          ))}
        </ClaimGrid>
      </Section>

      {/* ── Wallpapers (image tiles — keep) ──────────────────── */}
      <Section className="pt-0 pb-20">
        <SectionHead
          eyebrow="wallpapers"
          title={t.pets.wallpapersTitle}
          lede={t.pets.wallpapersSub}
        />

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {t.pets.wallpapers.map((w, i) => {
            const src = WALLPAPER_IMAGES[i] ?? WALLPAPER_IMAGES[0];
            return (
            <a
              key={w.title}
              href={src}
              download
              className="group frame block overflow-hidden"
              aria-label={`${t.pets.downloadLabel} — ${w.title}`}
            >
              <div className="relative aspect-[16/10] overflow-hidden">
                <img
                  src={src}
                  alt={w.title}
                  className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
                />
                <div
                  className="absolute inset-0 mix-blend-overlay"
                  style={{
                    background:
                      "linear-gradient(180deg, rgba(255,255,255,0.12) 0%, transparent 50%)",
                  }}
                />
                <div className="absolute right-3 top-3 inline-flex items-center gap-1.5 rounded-full bg-black/40 px-2.5 py-1 font-mono text-[10px] text-white opacity-0 backdrop-blur-md transition-opacity duration-200 group-hover:opacity-100">
                  <Icon name="download" className="h-3 w-3" />
                  {t.pets.downloadLabel}
                </div>
              </div>
              <div className="flex items-baseline justify-between gap-3 px-4 py-3">
                <p className="font-display text-sm font-medium text-text-primary">
                  {w.title}
                </p>
                <p className="font-mono text-[11px] text-text-muted">
                  {w.tag}
                </p>
              </div>
            </a>
            );
          })}
        </div>
      </Section>

      {/* ── GIF pack ────────────────────────────────────────── */}
      <Section className="pt-0 pb-24">
        <SectionHead
          eyebrow="animations"
          title={t.pets.gifsTitle}
          lede={t.pets.gifsSub}
        />

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {t.pets.gifs.map((g, i) => {
            const src = COMPANION_IMAGES[i] ?? COMPANION_IMAGES[0];
            return (
            <a
              key={g.name}
              href={src}
              download
              className="group frame block overflow-hidden"
              aria-label={`${t.pets.downloadLabel} — ${g.name}`}
            >
              <div className="relative flex aspect-square items-center justify-center overflow-hidden bg-surface/40">
                <img
                  src={src}
                  alt={g.name}
                  className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.04]"
                />
              </div>
              <div className="px-3 py-2.5">
                <p className="font-display text-sm font-medium text-text-primary">
                  {g.name}
                </p>
                <p className="font-mono text-[11px] text-text-muted">
                  {g.mood}
                </p>
              </div>
            </a>
            );
          })}
        </div>

        <p className="mt-8 font-mono text-[11px] tracking-[0.12em] text-text-muted/70">
          {t.pets.placeholderNote}
        </p>
      </Section>
    </>
  );
}
