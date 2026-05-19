import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

interface SectionProps {
  children: ReactNode;
  id?: string;
  className?: string;
  /** Slightly raised surface background */
  raised?: boolean;
  /** Tighter vertical rhythm — useful for back-to-back content sections */
  compact?: boolean;
}

export function Section({
  children,
  id,
  className,
  raised,
  compact,
}: SectionProps) {
  return (
    <section
      id={id}
      className={cn(
        "relative",
        compact ? "py-10 md:py-14" : "py-14 md:py-20",
        raised && "glass-subtle",
        className,
      )}
    >
      <div className="mx-auto max-w-6xl px-6">{children}</div>
    </section>
  );
}
