/**
 * Floating NavRail geometry:
 * - Horizontal: `gap-2` (8px) + rail + `gap-2` — matches tighter chrome than 12px gutters.
 * - Top: 10px — aligns with `.chat-fab-row` padding (`chat.css`) so the rail clears the shell in line with ChatFabBar.
 * Keep spacer + modal overlay inset in sync with `NavRail.tsx` positioning.
 */
export const NAV_RAIL_FLOAT_CLASSES = {
  spacerCollapsed: 'w-[5rem]',
  spacerExpanded: 'w-[17rem]',
  modalLeftCollapsed: 'left-[5rem]',
  modalLeftExpanded: 'left-[17rem]',
} as const;
