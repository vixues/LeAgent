import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import type { PdfDocument } from './pdfjs';

interface PdfThumbnailsProps {
  doc: PdfDocument;
  numPages: number;
  currentPage: number;
  onSelect: (page: number) => void;
}

export function PdfThumbnails({
  doc,
  numPages,
  currentPage,
  onSelect,
}: PdfThumbnailsProps) {
  return (
    <div className="flex h-full w-32 flex-shrink-0 flex-col overflow-y-auto border-r border-border bg-surface-sunken/40 p-2">
      {Array.from({ length: numPages }, (_, i) => i + 1).map((p) => (
        <Thumb
          key={p}
          doc={doc}
          page={p}
          active={p === currentPage}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}

function Thumb({
  doc,
  page,
  active,
  onSelect,
}: {
  doc: PdfDocument;
  page: number;
  active: boolean;
  onSelect: (page: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setVisible(true);
      },
      { rootMargin: '200px' },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    const render = async () => {
      const pageProxy = await doc.getPage(page);
      if (cancelled) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const targetWidth = 100;
      const base = pageProxy.getViewport({ scale: 1 });
      const scale = targetWidth / base.width;
      const viewport = pageProxy.getViewport({ scale });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      try {
        await pageProxy.render({ canvasContext: ctx, viewport }).promise;
      } catch {
        /* cancelled */
      }
    };
    void render();
    return () => {
      cancelled = true;
    };
  }, [visible, doc, page]);

  return (
    <div ref={ref} className="mb-2 flex flex-col items-center">
      <button
        type="button"
        onClick={() => onSelect(page)}
        className={cn(
          'overflow-hidden rounded border bg-white transition-shadow',
          active
            ? 'border-primary-500 ring-2 ring-primary-500/40'
            : 'border-border hover:border-primary-300',
        )}
      >
        <canvas ref={canvasRef} className="block h-auto w-[100px]" />
      </button>
      <span
        className={cn(
          'mt-0.5 text-[10px] tabular-nums',
          active ? 'font-semibold text-primary-600' : 'text-muted-foreground',
        )}
      >
        {page}
      </span>
    </div>
  );
}
