import { cn } from '@/lib/utils';

interface TypingIndicatorProps {
  className?: string;
}

export function TypingIndicator({ className }: TypingIndicatorProps) {
  return (
    <div className={cn('flex items-center gap-1 px-1 py-0.5', className)}>
      <span
        className="w-2 h-2 rounded-full bg-primary-400 animate-typing"
        style={{ animationDelay: '0ms' }}
        aria-hidden="true"
      />
      <span
        className="w-2 h-2 rounded-full bg-primary-400 animate-typing"
        style={{ animationDelay: '200ms' }}
        aria-hidden="true"
      />
      <span
        className="w-2 h-2 rounded-full bg-primary-400 animate-typing"
        style={{ animationDelay: '400ms' }}
        aria-hidden="true"
      />
    </div>
  );
}
