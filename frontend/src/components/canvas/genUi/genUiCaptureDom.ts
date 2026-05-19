/**
 * Temporarily removes scroll clipping (overflow/max dimensions) inside a subtree
 * so html-to-image captures full tables and ScrollArea content without scrollbars.
 */
export function expandScrollContainersForCapture(root: HTMLElement): () => void {
  const backups: Array<{ el: HTMLElement; cssText: string }> = [];
  const nodes: HTMLElement[] = [root, ...Array.from(root.querySelectorAll<HTMLElement>('*'))];

  for (const el of nodes) {
    const cs = getComputedStyle(el);
    const oy = cs.overflowY;
    const ox = cs.overflowX;
    const o = cs.overflow;
    const scrollLike =
      /auto|scroll|overlay/.test(o) ||
      /auto|scroll|overlay/.test(oy) ||
      /auto|scroll|overlay/.test(ox);
    const verticalClip = el.scrollHeight > el.clientHeight + 1;
    const horizontalClip = el.scrollWidth > el.clientWidth + 1;

    if (!scrollLike && !verticalClip && !horizontalClip) continue;

    backups.push({ el, cssText: el.style.cssText });
    el.style.setProperty('overflow', 'visible', 'important');
    el.style.setProperty('overflow-x', 'visible', 'important');
    el.style.setProperty('overflow-y', 'visible', 'important');
    el.style.setProperty('max-height', 'none', 'important');
    el.style.setProperty('max-width', 'none', 'important');
  }

  return () => {
    for (const { el, cssText } of backups) {
      el.style.cssText = cssText;
    }
  };
}

/** Force layout read after DOM mutations (expand). */
export function flushLayout(el: HTMLElement): void {
  void el.offsetHeight;
}

export async function nextDoubleFrame(): Promise<void> {
  await new Promise<void>((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
  );
}
