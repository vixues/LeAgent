import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui';
import { cn } from '@/lib/utils';
import { CodingProjectStatus } from '@/hooks/useCodingProjects';

const STATUS_STYLES: Record<CodingProjectStatus, string> = {
  idle:
    'bg-primary-100 text-primary-700 border-primary-200/80 dark:bg-primary-900/30 dark:text-primary-300 dark:border-primary-700/40',
  starting: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30',
  running: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30',
  stopping: 'bg-orange-500/15 text-orange-700 dark:text-orange-300 border-orange-500/30',
  crashed: 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30',
};

interface Props {
  status: CodingProjectStatus;
  className?: string;
}

export function CodingProjectStatusBadge({ status, className }: Props) {
  const { t } = useTranslation();
  const label = t(`codingProjects.status.${status}`);
  return (
    <Badge
      variant="outline"
      className={cn('text-[10px] uppercase tracking-wide', STATUS_STYLES[status], className)}
    >
      {label}
    </Badge>
  );
}
