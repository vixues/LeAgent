import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Info, X } from 'lucide-react';
import { Button, Card, CardContent } from '@/components/ui';
import { cn } from '@/lib/utils';
import { useProductMeta } from '@/hooks/useProductMeta';

interface AboutDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AboutDialog({ open, onOpenChange }: AboutDialogProps) {
  const { t } = useTranslation();
  const { data: meta } = useProductMeta();
  const [updateMsg, setUpdateMsg] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onOpenChange(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onOpenChange]);

  const onCheckUpdates = async () => {
    const fn = window.leagentDesktop?.checkForUpdates;
    if (!fn) {
      setUpdateMsg(t('about.updateNone'));
      return;
    }
    setChecking(true);
    setUpdateMsg(null);
    try {
      const r = await fn();
      setUpdateMsg(
        r?.ok ? t('about.updateAvailable') : r?.message || t('about.updateError'),
      );
    } catch {
      setUpdateMsg(t('about.updateError'));
    } finally {
      setChecking(false);
    }
  };

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <>
      <button
        type="button"
        aria-hidden
        tabIndex={-1}
        className="fixed inset-0 z-[80] cursor-default bg-black/[0.12] backdrop-blur-[1px] dark:bg-black/25"
        onClick={() => onOpenChange(false)}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="about-dialog-title"
        className={cn(
          'fixed z-[90] left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2',
          'w-[min(22rem,calc(100vw-1.5rem))] max-h-[min(85vh,36rem)] overflow-y-auto',
          'rounded-xl border border-border bg-surface shadow-xl',
          'animate-in fade-in-0 zoom-in-95 duration-200'
        )}
      >
        <button
          type="button"
          onClick={() => onOpenChange(false)}
          className={cn(
            'absolute right-3 top-3 p-1.5 rounded-lg z-10',
            'text-muted-foreground-tertiary hover:text-foreground',
            'hover:bg-surface-sunken dark:hover:bg-surface-elevated transition-colors'
          )}
          aria-label={t('common.close')}
        >
          <X className="w-4 h-4" />
        </button>

        <div className="px-5 pt-5 pb-4 border-b border-border/80">
          <div className="flex items-center gap-3 pr-8">
            <div className="rounded-full bg-primary/10 p-2.5 text-primary shrink-0">
              <Info className="h-5 w-5" aria-hidden />
            </div>
            <h2 id="about-dialog-title" className="text-lg font-semibold tracking-tight text-foreground">
              {t('about.title')}
            </h2>
          </div>
        </div>

        <div className="px-5 py-4 space-y-4">
          <Card className="border-border/80 shadow-sm">
            <CardContent className="p-4 space-y-2.5 text-sm">
              <div className="flex justify-between gap-4">
                <span className="text-muted-foreground">{t('about.product')}</span>
                <span className="font-medium text-right">{t('about.brandName')}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-muted-foreground">{t('about.authorLabel')}</span>
                <span className="font-medium text-right">{t('about.author')}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-muted-foreground">{t('about.version')}</span>
                <span className="font-mono text-right">{meta?.version ?? '—'}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-muted-foreground">{t('about.edition')}</span>
                <span className="text-right">{meta?.edition ?? '—'}</span>
              </div>
              <div className="flex justify-between gap-4 items-start">
                <span className="text-muted-foreground shrink-0">{t('about.build')}</span>
                <span className="font-mono text-xs text-right break-all">
                  {(meta?.build_git_sha || '—') + (meta?.build_time ? ` @ ${meta.build_time}` : '')}
                </span>
              </div>
            </CardContent>
          </Card>

          <div className="space-y-1.5 text-sm text-muted-foreground leading-relaxed">
            <p>{t('about.copyright')}</p>
            <p>{t('about.thirdParty')}</p>
            <p>
              {t('about.supportPrefix')}{' '}
              <a
                href={`mailto:${t('about.supportEmail')}`}
                className="text-primary hover:underline font-medium text-foreground/90"
              >
                {t('about.supportEmail')}
              </a>
            </p>
            <p>
              {t('about.githubLabel')}:{' '}
              <a
                href="https://github.com/vixues/LeAgent"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline font-medium text-foreground/90"
              >
                github.com/vixues/LeAgent
              </a>
            </p>
          </div>

          <div className="flex flex-wrap gap-2 pt-0.5">
            <Button variant="secondary" size="sm" disabled={checking} onClick={() => void onCheckUpdates()}>
              {checking ? t('about.updateChecking') : t('about.checkUpdates')}
            </Button>
          </div>
          {updateMsg ? <p className="text-sm text-foreground">{updateMsg}</p> : null}
        </div>
      </div>
    </>,
    document.body
  );
}
