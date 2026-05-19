import type { ReactNode } from "react";
import type { IconName } from "@/components/Icon";
import { Icon } from "@/components/Icon";
import { cn } from "@/lib/cn";

interface ClaimGridProps {
  children: ReactNode;
  /** Number of columns at md+ breakpoint (default 3) */
  columns?: 2 | 3;
  className?: string;
}

/**
 * Grid of short-copy claims separated by whitespace, not borders.
 * Each child should be a <Claim>. Hierarchy is carried entirely by
 * type weight and a thin top rule per item.
 */
export function ClaimGrid({
  children,
  columns = 3,
  className,
}: ClaimGridProps) {
  return (
    <div
      className={cn(
        "claim-grid",
        columns === 2 ? "claim-grid--2" : "claim-grid--3",
        className,
      )}
    >
      {children}
    </div>
  );
}

interface ClaimProps {
  /** Optional small label rendered above the title (e.g. an index) */
  label?: string;
  icon?: IconName;
  title: ReactNode;
  children: ReactNode;
  className?: string;
}

/**
 * A single claim: optional label + title + one short paragraph.
 * Designed for one-screen scannability — keep body to ~25 words.
 */
export function Claim({ label, icon, title, children, className }: ClaimProps) {
  return (
    <div className={cn("claim", className)}>
      {icon && (
        <span className="icon-tile mb-3" aria-hidden>
          <Icon name={icon} className="h-4 w-4" />
        </span>
      )}
      {label && <p className="claim__label">{label}</p>}
      <h3 className="claim__title">{title}</h3>
      <p className="claim__body">{children}</p>
    </div>
  );
}
