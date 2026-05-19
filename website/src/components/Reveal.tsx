import type { ReactNode, HTMLAttributes } from "react";
import { useReveal } from "@/lib/useReveal";
import { cn } from "@/lib/cn";

interface RevealProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  as?: "div" | "section" | "article";
  delay?: number;
}

export function Reveal({
  children,
  as: Tag = "div",
  className,
  delay,
  style,
  ...rest
}: RevealProps) {
  const ref = useReveal<HTMLDivElement>();

  return (
    <Tag
      ref={ref}
      className={cn("reveal", className)}
      style={{ ...style, animationDelay: delay ? `${delay}ms` : undefined }}
      {...rest}
    >
      {children}
    </Tag>
  );
}
