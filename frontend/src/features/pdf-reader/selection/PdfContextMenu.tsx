import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Camera,
  Copy,
  Languages,
  MessageSquarePlus,
  Quote,
  Sparkles,
  SquareDashedMousePointer,
} from 'lucide-react';

interface MenuState {
  x: number;
  y: number;
  text: string;
}

interface PdfContextMenuProps {
  /** Scrollable pages container; the menu mounts inside it (matches text menu). */
  containerRef: React.RefObject<HTMLElement | null>;
  onCopy: (text: string) => void;
  onExplain: (text: string) => void;
  onQuote: (text: string) => void;
  onTranslate: (text: string) => void;
  onAsk: (text: string) => void;
  onScreenshot: () => void;
  onToggleArea: () => void;
}

/**
 * Native-feeling right-click menu for the PDF pages. Adapts to context: when
 * text is selected it offers Explain / Copy / Quote / Translate / Ask; it always
 * offers page-level Screenshot + Area select.
 */
export function PdfContextMenu({
  containerRef,
  onCopy,
  onExplain,
  onQuote,
  onTranslate,
  onAsk,
  onScreenshot,
  onToggleArea,
}: PdfContextMenuProps) {
  const { t } = useTranslation();
  const [menu, setMenu] = useState<MenuState | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const close = useCallback(() => setMenu(null), []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const onContext = (e: MouseEvent) => {
      e.preventDefault();
      const selection = window.getSelection();
      const text =
        selection && !selection.isCollapsed ? selection.toString().trim() : '';
      const cRect = container.getBoundingClientRect();
      const MENU_W = 188;
      const menuH = text ? 244 : 88;
      const rawX = e.clientX - cRect.left;
      const rawY = e.clientY - cRect.top;
      setMenu({
        x: Math.max(4, Math.min(rawX, cRect.width - MENU_W - 4)),
        y: Math.max(4, Math.min(rawY, cRect.height - menuH - 4)),
        text,
      });
    };

    container.addEventListener('contextmenu', onContext);
    return () => container.removeEventListener('contextmenu', onContext);
  }, [containerRef]);

  useEffect(() => {
    if (!menu) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    const onScroll = () => close();
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    containerRef.current?.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
      containerRef.current?.removeEventListener('scroll', onScroll);
    };
  }, [menu, close, containerRef]);

  if (!menu) return null;

  const hasText = menu.text.length > 0;
  const run = (fn: () => void) => {
    fn();
    close();
  };

  return (
    <div
      ref={menuRef}
      className="absolute z-50 min-w-[180px] overflow-hidden rounded-lg border border-border-subtle bg-surface/95 py-1 shadow-xl ring-1 ring-black/[0.04] backdrop-blur dark:ring-white/[0.06]"
      style={{ left: menu.x, top: menu.y }}
      onContextMenu={(e) => e.preventDefault()}
    >
      {hasText ? (
        <>
          <MenuItem
            icon={<Sparkles className="h-4 w-4 text-primary-600" />}
            label={t('pdfReader.selection.explain', { defaultValue: 'Explain' })}
            onClick={() => run(() => onExplain(menu.text))}
          />
          <MenuItem
            icon={<Copy className="h-4 w-4" />}
            label={t('pdfReader.selection.copy', { defaultValue: 'Copy' })}
            onClick={() => run(() => onCopy(menu.text))}
          />
          <MenuItem
            icon={<Quote className="h-4 w-4" />}
            label={t('pdfReader.selection.insert', { defaultValue: 'Quote' })}
            onClick={() => run(() => onQuote(menu.text))}
          />
          <MenuItem
            icon={<Languages className="h-4 w-4" />}
            label={t('pdfReader.selection.translate', { defaultValue: 'Translate' })}
            onClick={() => run(() => onTranslate(menu.text))}
          />
          <MenuItem
            icon={<MessageSquarePlus className="h-4 w-4" />}
            label={t('pdfReader.selection.ask', { defaultValue: 'Ask' })}
            onClick={() => run(() => onAsk(menu.text))}
          />
          <div className="my-1 h-px bg-border-subtle" />
        </>
      ) : null}
      <MenuItem
        icon={<Camera className="h-4 w-4" />}
        label={t('pdfReader.toolbar.screenshot', { defaultValue: 'Screenshot' })}
        onClick={() => run(onScreenshot)}
      />
      <MenuItem
        icon={<SquareDashedMousePointer className="h-4 w-4" />}
        label={t('pdfReader.toolbar.areaSelect', { defaultValue: 'Area select' })}
        onClick={() => run(onToggleArea)}
      />
    </div>
  );
}

function MenuItem({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-2.5 whitespace-nowrap px-3 py-1.5 text-left text-xs font-medium text-foreground transition-colors hover:bg-surface-sunken"
    >
      <span className="shrink-0 text-muted-foreground">{icon}</span>
      {label}
    </button>
  );
}
