import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useDesktop } from '@/hooks/useDesktop';
import { useThemeStore, resolveTheme } from '@/stores/theme';

const DRAG = '[-webkit-app-region:drag]';
const NO_DRAG = '[-webkit-app-region:no-drag]';

/** Windows native overlay symbol colors per resolved theme. */
function overlaySymbolColor(resolved: 'light' | 'dark'): string {
  return resolved === 'dark' ? '#e8e8ea' : '#3c4043';
}

interface ControlButtonProps {
  label: string;
  onClick: () => void;
  danger?: boolean;
  children: React.ReactNode;
}

function ControlButton({ label, onClick, danger, children }: ControlButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={cn(
        NO_DRAG,
        'flex h-full w-[46px] items-center justify-center text-muted-foreground transition-colors',
        'hover:text-foreground',
        danger
          ? 'hover:bg-red-600 hover:text-white'
          : 'hover:bg-surface-sunken dark:hover:bg-surface-elevated',
      )}
    >
      {children}
    </button>
  );
}

/** 10px system-style window glyphs (Windows/Fluent metrics). */
function GlyphMinimize() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden>
      <rect x="0" y="4.5" width="10" height="1" fill="currentColor" />
    </svg>
  );
}

function GlyphMaximize() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden>
      <rect x="0.5" y="0.5" width="9" height="9" fill="none" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}

function GlyphRestore() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden>
      <rect x="0.5" y="2.5" width="7" height="7" fill="none" stroke="currentColor" strokeWidth="1" />
      <path d="M2.5 2.5V0.5H9.5V7.5H7.5" fill="none" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}

function GlyphClose() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden>
      <path d="M0.5 0.5L9.5 9.5M9.5 0.5L0.5 9.5" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  );
}

/**
 * Professional, system-native title bar for the Electron desktop shell.
 *  - macOS: native traffic lights (we just reserve space + provide a drag region).
 *  - Windows: native Window Controls Overlay (we keep its area clear + theme its symbols).
 *  - Linux: custom minimize / maximize / close controls.
 * Renders nothing in the browser.
 */
export function TitleBar() {
  const { t } = useTranslation();
  const { isDesktop, titleBarStyle, bridge } = useDesktop();
  const theme = useThemeStore((s) => s.theme);
  const [maximized, setMaximized] = useState(false);

  // Reserve vertical space for the floating NavRail and page content.
  useEffect(() => {
    if (!isDesktop) return;
    const root = document.documentElement;
    root.style.setProperty('--titlebar-height', '36px');
    return () => {
      root.style.removeProperty('--titlebar-height');
    };
  }, [isDesktop]);

  // Track maximize state for the restore/maximize glyph (custom controls).
  useEffect(() => {
    if (!isDesktop || !bridge?.window) return;
    let active = true;
    void bridge.window.isMaximized().then((v) => {
      if (active) setMaximized(v);
    });
    const off = bridge.window.onMaximizeChanged((v) => setMaximized(v));
    return () => {
      active = false;
      off();
    };
  }, [isDesktop, bridge]);

  // Keep the native Windows overlay symbols in sync with the app theme.
  useEffect(() => {
    if (!isDesktop || titleBarStyle !== 'overlay' || !bridge?.window) return;
    const apply = () => {
      void bridge.window.setOverlay({
        color: '#00000000',
        symbolColor: overlaySymbolColor(resolveTheme(theme)),
      });
    };
    apply();
    if (theme !== 'system') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, [isDesktop, titleBarStyle, bridge, theme]);

  const toggleMaximize = useCallback(() => {
    void bridge?.window?.maximizeToggle();
  }, [bridge]);

  const onDoubleClick = useCallback(() => {
    if (titleBarStyle === 'custom') toggleMaximize();
  }, [titleBarStyle, toggleMaximize]);

  if (!isDesktop) return null;

  const isMac = titleBarStyle === 'mac';
  const isCustom = titleBarStyle === 'custom';

  return (
    <header
      onDoubleClick={onDoubleClick}
      className={cn(
        DRAG,
        'flex h-9 flex-shrink-0 select-none items-center justify-between',
        'border-b border-border/60 bg-background/95 backdrop-blur',
        isMac ? 'pl-[78px] pr-3' : 'pl-3 pr-0',
      )}
    >
      <div className={cn('flex min-w-0 items-center gap-2', NO_DRAG)}>
        <img src="/brand/logo.svg" alt="" className="h-4 w-4 flex-shrink-0" draggable={false} />
        <span className="truncate text-[13px] font-medium tracking-tight text-muted-foreground">
          LeAgent
        </span>
      </div>

      {/* Empty flexible drag region in the middle keeps the bar draggable. */}
      <div className="h-full flex-1" />

      {isCustom ? (
        <div className={cn('flex h-full items-stretch', NO_DRAG)}>
          <ControlButton label={t('common.window.minimize')} onClick={() => void bridge?.window?.minimize()}>
            <GlyphMinimize />
          </ControlButton>
          <ControlButton
            label={maximized ? t('common.window.restore') : t('common.window.maximize')}
            onClick={toggleMaximize}
          >
            {maximized ? <GlyphRestore /> : <GlyphMaximize />}
          </ControlButton>
          <ControlButton label={t('common.window.close')} onClick={() => void bridge?.window?.close()} danger>
            <GlyphClose />
          </ControlButton>
        </div>
      ) : (
        // Windows overlay reserves its own native control strip on the right.
        <div className={cn('h-full', titleBarStyle === 'overlay' ? 'w-[138px]' : 'w-3')} aria-hidden />
      )}
    </header>
  );
}
