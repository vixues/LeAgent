import { memo } from 'react';

import { cn } from '@/lib/utils';

import type { InputSlot } from '../graph/objectInfo';

interface NodeWidgetProps {
  slot: InputSlot;
  value: unknown;
  onChange: (value: unknown) => void;
  /** Disabled when the input is driven by a link. */
  connected?: boolean;
}

/**
 * Render the inline editing widget for a node input, driven by the widget
 * kind the backend declared in `/object_info` (litegraph-style inline
 * widgets). When the slot is connected, the widget is shown read-only since
 * the value comes from upstream.
 */
function NodeWidgetImpl({ slot, value, onChange, connected }: NodeWidgetProps) {
  const baseField =
    'nodrag w-full rounded border border-border bg-background px-1.5 py-0.5 text-xs text-foreground disabled:opacity-50';

  if (connected) {
    return (
      <div className="text-[10px] italic text-muted-foreground">
        {slot.id} ← linked
      </div>
    );
  }

  switch (slot.widget) {
    case 'string':
      return slot.multiline ? (
        <textarea
          className={cn(baseField, 'resize-y min-h-[44px]')}
          value={typeof value === 'string' ? value : ''}
          placeholder={slot.tooltip ?? slot.id}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          type="text"
          className={baseField}
          value={typeof value === 'string' ? value : ''}
          placeholder={slot.tooltip ?? slot.id}
          onChange={(e) => onChange(e.target.value)}
        />
      );

    case 'int':
    case 'float':
      return (
        <input
          type="number"
          className={baseField}
          value={value === undefined || value === null ? '' : Number(value)}
          min={slot.min}
          max={slot.max}
          step={slot.step ?? (slot.widget === 'int' ? 1 : 0.01)}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === '') return onChange(undefined);
            onChange(slot.widget === 'int' ? parseInt(raw, 10) : parseFloat(raw));
          }}
        />
      );

    case 'toggle':
      return (
        <label className="nodrag flex items-center gap-1.5 text-xs text-foreground">
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
          />
          {slot.id}
        </label>
      );

    case 'combo':
      return (
        <select
          className={baseField}
          value={typeof value === 'string' ? value : (slot.default as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
        >
          {(slot.choices ?? []).map((choice) => (
            <option key={choice} value={choice}>
              {choice}
            </option>
          ))}
        </select>
      );

    case 'file':
      return (
        <input
          type="text"
          className={baseField}
          value={typeof value === 'string' ? value : ''}
          placeholder="file id or path"
          onChange={(e) => onChange(e.target.value)}
        />
      );

    case 'datetime':
      return (
        <input
          type="datetime-local"
          className={baseField}
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value)}
        />
      );

    default:
      return null;
  }
}

export const NodeWidget = memo(NodeWidgetImpl);
