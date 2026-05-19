import { cn } from "@/lib/cn";

export interface FeatureShotItem {
  id: string;
  title: string;
  description: string;
  label: string;
  imageSrc: string;
}

interface FeatureShotProps {
  item: FeatureShotItem;
  index: number;
  placeholderNote: string;
  className?: string;
}

export function FeatureShot({
  item,
  index,
  placeholderNote,
  className,
}: FeatureShotProps) {
  const num = String(index + 1).padStart(2, "0");

  return (
    <article className={cn("feature-shot frame", className)}>
      <div className="feature-shot__preview">
        <img
          src={item.imageSrc}
          alt={item.title}
          className="feature-shot__image"
          loading="lazy"
          onError={(e) => {
            const img = e.currentTarget;
            img.style.display = "none";
            const fallback = img.nextElementSibling;
            if (fallback instanceof HTMLElement) fallback.hidden = false;
          }}
        />
        <Placeholder num={num} label={item.label} note={placeholderNote} />
      </div>
      <div className="feature-shot__meta">
        <p className="feature-shot__eyebrow">{item.label}</p>
        <h3 className="feature-shot__title">{item.title}</h3>
        <p className="feature-shot__body">{item.description}</p>
      </div>
    </article>
  );
}

function Placeholder({
  num,
  label,
  note,
}: {
  num: string;
  label: string;
  note: string;
}) {
  return (
    <div className="feature-shot__placeholder" hidden>
      <span className="feature-shot__num">{num}</span>
      <span className="feature-shot__label">{label}</span>
      <span className="feature-shot__note">{note}</span>
    </div>
  );
}
