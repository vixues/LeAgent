import { cn } from '@/lib/utils';
import type { PetClipState } from '@/lib/petSettings';

export function ActionSlot({
  state,
  label,
  selected,
  onSelect,
}: {
  state: PetClipState;
  label: string;
  selected: boolean;
  onSelect: (s: PetClipState) => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(state)}
        className={cn(
          'w-full rounded-lg px-2.5 py-1.5 text-left text-xs font-medium transition-colors',
          selected
            ? 'bg-primary-100 text-primary-900 dark:bg-primary-950/50 dark:text-primary-100'
            : 'text-foreground hover:bg-surface-sunken',
        )}
      >
        {label}
      </button>
    </li>
  );
}
