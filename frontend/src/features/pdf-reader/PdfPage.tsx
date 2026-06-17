import { useEffect, useRef, useState } from 'react';
import { pdfjsLib, type PdfDocument } from './pdfjs';
import './pdfTextLayer.css';

export interface AreaSelection {
  page: number;
  /** Rect in rendered canvas pixels (device-independent, at current scale). */
  cssRect: { x: number; y: number; width: number; height: number };
  /** Rect in PDF point space (scale 1), origin top-left. */
  pdfRect: { x0: number; y0: number; x1: number; y1: number };
  canvas: HTMLCanvasElement;
}

interface PdfPageProps {
  doc: PdfDocument;
  pageNumber: number;
  scale: number;
  rotation: number;
  /** When true, dragging selects a rectangular region instead of text. */
  areaMode: boolean;
  onAreaSelected: (sel: AreaSelection) => void;
  onVisible?: (page: number) => void;
  /** Region to highlight on this page, in PDF points (scale 1, top-left origin). */
  highlightRect?: { x: number; y: number; width: number; height: number } | null;
}

/** Renders one PDF page: canvas + selectable text layer + optional area-select overlay. */
export function PdfPage({
  doc,
  pageNumber,
  scale,
  rotation,
  areaMode,
  onAreaSelected,
  onVisible,
  highlightRect,
}: PdfPageProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textLayerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const [dragRect, setDragRect] = useState<{
    x: number;
    y: number;
    w: number;
    h: number;
  } | null>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);

  // Render canvas + text layer whenever inputs change.
  useEffect(() => {
    let cancelled = false;
    const render = async () => {
      const page = await doc.getPage(pageNumber);
      if (cancelled) return;
      const viewport = page.getViewport({ scale, rotation });
      const canvas = canvasRef.current;
      const textLayerDiv = textLayerRef.current;
      if (!canvas || !textLayerDiv) return;

      const outputScale = window.devicePixelRatio || 1;
      canvas.width = Math.floor(viewport.width * outputScale);
      canvas.height = Math.floor(viewport.height * outputScale);
      canvas.style.width = `${Math.floor(viewport.width)}px`;
      canvas.style.height = `${Math.floor(viewport.height)}px`;
      setSize({ w: Math.floor(viewport.width), h: Math.floor(viewport.height) });

      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      const transform =
        outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : undefined;

      const renderTask = page.render({
        canvasContext: ctx,
        viewport,
        transform,
      });
      try {
        await renderTask.promise;
      } catch {
        return;
      }
      if (cancelled) return;

      // Text layer
      textLayerDiv.replaceChildren();
      textLayerDiv.style.setProperty('--scale-factor', String(scale));
      textLayerDiv.style.width = `${Math.floor(viewport.width)}px`;
      textLayerDiv.style.height = `${Math.floor(viewport.height)}px`;
      const textContent = await page.getTextContent();
      if (cancelled) return;
      const textLayer = new pdfjsLib.TextLayer({
        textContentSource: textContent,
        container: textLayerDiv,
        viewport,
      });
      await textLayer.render();
    };
    void render();
    return () => {
      cancelled = true;
    };
  }, [doc, pageNumber, scale, rotation]);

  // Report visibility for the toolbar page indicator.
  useEffect(() => {
    if (!onVisible || !wrapRef.current) return;
    const el = wrapRef.current;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting && e.intersectionRatio > 0.5) onVisible(pageNumber);
        }
      },
      { threshold: [0.5] },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [onVisible, pageNumber]);

  const handlePointerDown = (e: React.PointerEvent) => {
    if (!areaMode) return;
    const rect = e.currentTarget.getBoundingClientRect();
    dragStart.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    setDragRect({ x: dragStart.current.x, y: dragStart.current.y, w: 0, h: 0 });
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!areaMode || !dragStart.current) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    const x = Math.min(cx, dragStart.current.x);
    const y = Math.min(cy, dragStart.current.y);
    setDragRect({
      x,
      y,
      w: Math.abs(cx - dragStart.current.x),
      h: Math.abs(cy - dragStart.current.y),
    });
  };

  const handlePointerUp = () => {
    if (!areaMode || !dragStart.current || !dragRect) {
      dragStart.current = null;
      return;
    }
    const canvas = canvasRef.current;
    if (canvas && dragRect.w > 6 && dragRect.h > 6) {
      onAreaSelected({
        page: pageNumber,
        cssRect: {
          x: dragRect.x,
          y: dragRect.y,
          width: dragRect.w,
          height: dragRect.h,
        },
        pdfRect: {
          x0: dragRect.x / scale,
          y0: dragRect.y / scale,
          x1: (dragRect.x + dragRect.w) / scale,
          y1: (dragRect.y + dragRect.h) / scale,
        },
        canvas,
      });
    }
    dragStart.current = null;
    setDragRect(null);
  };

  // The area-select crop uses device pixels, so translate css rect by outputScale.
  // (We pass the canvas + css rect to the caller and let it scale.)

  return (
    <div
      ref={wrapRef}
      data-page={pageNumber}
      className="relative mx-auto my-4 shadow-md ring-1 ring-border"
      style={{ width: size.w || undefined, height: size.h || undefined }}
    >
      <canvas ref={canvasRef} className="block" />
      <div
        ref={textLayerRef}
        className="leagent-pdf-textLayer"
        style={{ pointerEvents: areaMode ? 'none' : 'auto' }}
      />
      {highlightRect && (
        <div
          className="pointer-events-none absolute z-20 rounded-sm ring-2 ring-primary-500 bg-primary-400/20 shadow-[0_0_0_9999px_rgba(0,0,0,0.04)] animate-pulse"
          style={{
            left: highlightRect.x * scale,
            top: highlightRect.y * scale,
            width: Math.max(8, highlightRect.width * scale),
            height: Math.max(8, highlightRect.height * scale),
          }}
        />
      )}
      {areaMode && (
        <div
          className="absolute inset-0 z-10 cursor-crosshair"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
        >
          {dragRect && (
            <div
              className="absolute border-2 border-primary-500 bg-primary-500/10"
              style={{
                left: dragRect.x,
                top: dragRect.y,
                width: dragRect.w,
                height: dragRect.h,
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}
