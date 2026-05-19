import { ChevronDown } from 'lucide-react';
import type { PetClipState } from '@/lib/petSettings';
import { cn } from '@/lib/utils';
import { ACTION_STUDIO_MAIN_COLUMN_HEIGHT_CLASS } from './actionStudioConstants';
import { STUDIO_STATE_GROUPS } from './studioStateGroups';
import { ActionSlot } from './ActionSlot';

function stateLabel(t: (k: string) => string, s: PetClipState): string {
  if (s === 'lookAround') return t('petSpace.manualMode.lookAround');
  if (s === 'idle') return t('petSpace.actionState.idle.name');
  if (['none', 'breath', 'blink', 'float', 'tailWag', 'hop'].includes(s)) {
    return t(`petSpace.idleAnimation.${s}`);
  }
  return t(`petSpace.actionState.${s}.name`);
}

export function ActionGroups({
  selected,
  onSelect,
  t,
}: {
  selected: PetClipState | null;
  onSelect: (s: PetClipState) => void;
  t: (k: string) => string;
}) {
  return (
    <div
      className={cn(
        ACTION_STUDIO_MAIN_COLUMN_HEIGHT_CLASS,
        'shrink-0 overflow-y-auto overscroll-contain rounded-xl border border-border bg-surface-sunken/10 p-2 [scrollbar-gutter:stable]',
      )}
    >
      <div className="flex flex-col gap-2">
        {STUDIO_STATE_GROUPS.map((g) => (
          <details
            key={g.id}
            name="pet-studio-action-groups"
            className="group rounded-xl border border-border bg-surface-sunken/20 open:bg-surface-sunken/30"
          >
            <summary className="sticky top-0 z-10 flex cursor-pointer list-none items-center gap-2 rounded-t-xl border-b border-border-subtle bg-surface-sunken/20 px-3 py-2 text-sm font-semibold text-foreground backdrop-blur-sm group-open:bg-surface-sunken/30 [&::-webkit-details-marker]:hidden">
              <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
              {t(`petSpace.studio.group.${g.id}`)}
            </summary>
            <ul className="space-y-0.5 border-t border-border-subtle p-1.5">
              {g.states.map((s) => (
                <ActionSlot
                  key={s}
                  state={s}
                  label={stateLabel(t, s)}
                  selected={selected === s}
                  onSelect={onSelect}
                />
              ))}
            </ul>
          </details>
        ))}
      </div>
    </div>
  );
}
