import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeftRight, Link2, Link2Off } from 'lucide-react';

import { cn } from '@/lib/utils';

import type { InputSlot } from '../graph/objectInfo';

interface RatioPreset {
  label: string;
  w: number;
  h: number;
}

/** Common generation aspect ratios (portrait + landscape + square). */
const RATIO_PRESETS: RatioPreset[] = [
  { label: '1:1', w: 1, h: 1 },
  { label: '3:2', w: 3, h: 2 },
  { label: '2:3', w: 2, h: 3 },
  { label: '4:3', w: 4, h: 3 },
  { label: '3:4', w: 3, h: 4 },
  { label: '16:9', w: 16, h: 9 },
  { label: '9:16', w: 9, h: 16 },
];

const RATIO_TOLERANCE = 0.02;
const DEFAULT_BASE = 1024;

/** A node exposes the combined size control when it has both width + height numeric slots. */
export function hasImageSizeSlots(inputs: InputSlot[]): boolean {
  const w = inputs.find((s) => s.id === 'width');
  const h = inputs.find((s) => s.id === 'height');
  const numeric = (s?: InputSlot) => Boolean(s && (s.widget === 'int' || s.widget === 'float'));
  return numeric(w) && numeric(h);
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(Math.max(v, lo), hi);
}

function snap(v: number, step: number, lo: number, hi: number): number {
  const s = step > 0 ? step : 1;
  return clamp(Math.round(v / s) * s, lo, hi);
}

interface DimInputProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onCommit: (v: number) => void;
}

/** Single dimension field: edits freely, snaps to step on blur / Enter. */
function DimInput({ label, value, min, max, step, onCommit }: DimInputProps) {
  const [draft, setDraft] = useState(String(value));

  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  const commit = () => {
    const n = Number.parseFloat(draft);
    if (Number.isFinite(n)) onCommit(n);
    else setDraft(String(value));
  };

  return (
    <div className="relative min-w-0 flex-1">
      <span className="pointer-events-none absolute left-1.5 top-1/2 -translate-y-1/2 text-[9px] font-medium uppercase text-muted-foreground-tertiary">
        {label}
      </span>
      <input
        type="number"
        className="nodrag w-full rounded border border-border bg-background py-0.5 pl-5 pr-1 text-right text-xs tabular-nums text-foreground focus:border-primary-400 focus:outline-none"
        value={draft}
        min={min}
        max={max}
        step={step}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            commit();
            (e.target as HTMLInputElement).blur();
          }
        }}
      />
    </div>
  );
}

interface ImageSizeControlProps {
  width: number;
  height: number;
  widthSlot: InputSlot;
  heightSlot: InputSlot;
  onChange: (width: number, height: number) => void;
}

/**
 * Professional-but-compact image size control: aspect-ratio presets, paired
 * W/H fields, an orientation swap, and an optional ratio lock — a single
 * cohesive panel that replaces the two bare width/height number inputs.
 */
function ImageSizeControlImpl({
  width,
  height,
  widthSlot,
  heightSlot,
  onChange,
}: ImageSizeControlProps) {
  const [locked, setLocked] = useState(false);

  const wMin = widthSlot.min ?? 1;
  const wMax = widthSlot.max ?? 8192;
  const wStep = widthSlot.step ?? 1;
  const hMin = heightSlot.min ?? 1;
  const hMax = heightSlot.max ?? 8192;
  const hStep = heightSlot.step ?? 1;

  const ratio = width > 0 && height > 0 ? width / height : 1;

  const activePreset = useMemo(
    () =>
      RATIO_PRESETS.find((p) => Math.abs(p.w / p.h - ratio) < RATIO_TOLERANCE)?.label ?? null,
    [ratio],
  );

  const applyPreset = useCallback(
    (preset: RatioPreset) => {
      const target = preset.w / preset.h;
      const base = Math.max(width, height) || DEFAULT_BASE;
      const w = target >= 1 ? base : base * target;
      const h = target >= 1 ? base / target : base;
      onChange(snap(w, wStep, wMin, wMax), snap(h, hStep, hMin, hMax));
    },
    [width, height, onChange, wStep, wMin, wMax, hStep, hMin, hMax],
  );

  const swap = useCallback(() => {
    onChange(snap(height, wStep, wMin, wMax), snap(width, hStep, hMin, hMax));
  }, [width, height, onChange, wStep, wMin, wMax, hStep, hMin, hMax]);

  const setWidth = useCallback(
    (raw: number) => {
      const w = snap(raw, wStep, wMin, wMax);
      if (locked && height > 0) {
        onChange(w, snap(w / ratio, hStep, hMin, hMax));
      } else {
        onChange(w, height);
      }
    },
    [locked, height, ratio, onChange, wStep, wMin, wMax, hStep, hMin, hMax],
  );

  const setHeight = useCallback(
    (raw: number) => {
      const h = snap(raw, hStep, hMin, hMax);
      if (locked && width > 0) {
        onChange(snap(h * ratio, wStep, wMin, wMax), h);
      } else {
        onChange(width, h);
      }
    },
    [locked, width, ratio, onChange, wStep, wMin, wMax, hStep, hMin, hMax],
  );

  return (
    <div className="nodrag flex flex-col gap-1.5">
      <div className="grid grid-cols-4 gap-1">
        {RATIO_PRESETS.map((preset) => {
          const active = preset.label === activePreset;
          return (
            <button
              key={preset.label}
              type="button"
              title={`${preset.label}`}
              onClick={() => applyPreset(preset)}
              className={cn(
                'rounded border px-1 py-0.5 text-[9px] font-medium tabular-nums transition-colors',
                active
                  ? 'border-primary-400 bg-primary-50 text-primary-600 dark:border-primary-600 dark:bg-primary-900/30 dark:text-primary-300'
                  : 'border-border bg-background text-muted-foreground hover:border-primary-300 hover:text-foreground',
              )}
            >
              {preset.label}
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-1">
        <DimInput
          label="W"
          value={width}
          min={wMin}
          max={wMax}
          step={wStep}
          onCommit={setWidth}
        />
        <button
          type="button"
          title="Swap width / height"
          onClick={swap}
          className="nodrag flex h-6 w-6 shrink-0 items-center justify-center rounded border border-border bg-background text-muted-foreground transition-colors hover:border-primary-300 hover:text-foreground"
        >
          <ArrowLeftRight className="h-3 w-3" aria-hidden />
        </button>
        <DimInput
          label="H"
          value={height}
          min={hMin}
          max={hMax}
          step={hStep}
          onCommit={setHeight}
        />
        <button
          type="button"
          aria-pressed={locked}
          title={locked ? 'Aspect ratio locked' : 'Lock aspect ratio'}
          onClick={() => setLocked((v) => !v)}
          className={cn(
            'nodrag flex h-6 w-6 shrink-0 items-center justify-center rounded border transition-colors',
            locked
              ? 'border-primary-400 bg-primary-50 text-primary-600 dark:border-primary-600 dark:bg-primary-900/30 dark:text-primary-300'
              : 'border-border bg-background text-muted-foreground hover:border-primary-300 hover:text-foreground',
          )}
        >
          {locked ? (
            <Link2 className="h-3 w-3" aria-hidden />
          ) : (
            <Link2Off className="h-3 w-3" aria-hidden />
          )}
        </button>
      </div>
    </div>
  );
}

export const ImageSizeControl = memo(ImageSizeControlImpl);
