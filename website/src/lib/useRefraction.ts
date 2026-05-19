import { useEffect } from "react";

const SEL = ".card-interactive, .btn-primary, .btn-ghost";

/**
 * Document-level event delegation that feeds `--rx` / `--ry` CSS custom
 * properties (0–100 %) into every hovered card or button, enabling the
 * cursor-tracking prismatic refraction effect defined in index.css.
 *
 * Mount once in <Layout>.
 */
export function useRefraction() {
  useEffect(() => {
    let active: HTMLElement | null = null;

    function onMove(e: PointerEvent) {
      const el = (e.target as Element).closest?.(SEL) as HTMLElement | null;

      if (el !== active) {
        if (active) {
          active.style.removeProperty("--rx");
          active.style.removeProperty("--ry");
        }
        active = el;
      }

      if (!el) return;

      const r = el.getBoundingClientRect();
      const x = ((e.clientX - r.left) / r.width) * 100;
      const y = ((e.clientY - r.top) / r.height) * 100;
      el.style.setProperty("--rx", `${x}%`);
      el.style.setProperty("--ry", `${y}%`);
    }

    function onLeave() {
      if (active) {
        active.style.removeProperty("--rx");
        active.style.removeProperty("--ry");
        active = null;
      }
    }

    document.addEventListener("pointermove", onMove, { passive: true });
    document.documentElement.addEventListener("pointerleave", onLeave);

    return () => {
      document.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("pointerleave", onLeave);
    };
  }, []);
}
