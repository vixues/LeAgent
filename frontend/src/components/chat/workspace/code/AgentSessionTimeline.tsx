import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import type { AgentSessionEvent } from '@/lib/agentSessionEvents';
import { SessionEventRow } from './SessionEventRow';

interface AgentSessionTimelineProps {
  events: AgentSessionEvent[];
  isExpanded: (id: string) => boolean;
  onToggle: (id: string) => void;
  wrap: boolean;
  /** When set, scroll the matching row into view (rail jump-to-event). */
  scrollTargetId?: string | null;
  onScrolled?: () => void;
  className?: string;
}

export function AgentSessionTimeline({
  events,
  isExpanded,
  onToggle,
  wrap,
  scrollTargetId,
  onScrolled,
  className,
}: AgentSessionTimelineProps) {
  const { t } = useTranslation();
  const rowRefs = useRef(new Map<string, HTMLDivElement>());

  useEffect(() => {
    if (!scrollTargetId) return;
    const el = rowRefs.current.get(scrollTargetId);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      el.classList.add('ring-2', 'ring-primary-500/40');
      const timer = window.setTimeout(() => {
        el.classList.remove('ring-2', 'ring-primary-500/40');
      }, 1200);
      onScrolled?.();
      return () => window.clearTimeout(timer);
    }
    onScrolled?.();
  }, [scrollTargetId, onScrolled]);

  if (events.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 py-10 text-center">
        <p className="max-w-[220px] text-[11px] leading-relaxed text-muted-foreground/70">
          {t('chat.workspace.agent.timelineEmptyFiltered', {
            defaultValue: 'No activity matches the current filter.',
          })}
        </p>
      </div>
    );
  }

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {events.map((event) => (
        <SessionEventRow
          key={event.id}
          event={event}
          expanded={isExpanded(event.id)}
          wrap={wrap}
          onToggle={() => onToggle(event.id)}
          innerRef={(el) => {
            if (el) rowRefs.current.set(event.id, el);
            else rowRefs.current.delete(event.id);
          }}
        />
      ))}
    </div>
  );
}
