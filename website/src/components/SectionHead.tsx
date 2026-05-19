import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

interface SectionHeadProps {
  /** Small uppercase label rendered above the title */
  eyebrow?: string;
  /** Display title */
  title: ReactNode;
  /** Optional supporting paragraph */
  lede?: ReactNode;
  /** Optional trailing element (CTA, controls) on the right column */
  aside?: ReactNode;
  className?: string;
}

/**
 * Editorial section header. Eyebrow → title → optional lede / aside,
 * laid out as a 12-column asymmetric block. Deliberately calm —
 * no leading numerals or connecting rules — so it reads as a single
 * gesture rather than a chopped sub-section.
 */
export function SectionHead({
  eyebrow,
  title,
  lede,
  aside,
  className,
}: SectionHeadProps) {
  return (
    <header className={cn("mb-12 md:mb-16", className)}>
      {eyebrow && <p className="eyebrow mb-5">{eyebrow}</p>}

      <div className="grid items-end gap-x-12 gap-y-6 md:grid-cols-12">
        <h2 className="font-display text-3xl font-semibold leading-[1.08] tracking-tight text-text-primary md:col-span-7 md:text-4xl lg:text-5xl">
          {title}
        </h2>

        {(lede || aside) && (
          <div className="md:col-span-5 md:pb-1">
            {lede && (
              <p className="text-base leading-relaxed text-text-secondary">
                {lede}
              </p>
            )}
            {aside && <div className={lede ? "mt-4" : undefined}>{aside}</div>}
          </div>
        )}
      </div>
    </header>
  );
}
