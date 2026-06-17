import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Copy,
  Languages,
  MessageSquarePlus,
  Quote,
  Sparkles,
  X,
} from 'lucide-react';

interface SelectionState {
  text: string;
  x: number;
  y: number;
}

interface TextSelectionMenuProps {
  /** Container the selection must originate within (the scrollable pages area). */
  containerRef: React.RefObject<HTMLElement | null>;
  onInsert: (text: string) => void;
  onTranslate: (text: string) => void;
  onAsk: (text: string) => void;
  onCopy: (text: string) => void;
  onExplain: (text: string) => void;
}

/** Floating action bar shown above a text selection inside the PDF pages. */
export function TextSelectionMenu({
  containerRef,
  onInsert,
  onTranslate,
  onAsk,
  onCopy,
  onExplain,
}: TextSelectionMenuProps) {
  const { t } = useTranslation();
  const [sel, setSel] = useState<SelectionState | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const compute = useCallback(() => {
    const selection = window.getSelection();
    const container = containerRef.current;
    if (!selection || selection.isCollapsed || !container) {
      setSel(null);
      return;
    }
    const text = selection.toString().trim();
    if (!text) {
      setSel(null);
      return;
    }
    const anchorNode = selection.anchorNode;
    if (!anchorNode || !container.contains(anchorNode)) {
      setSel(null);
      return;
    }
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    const cRect = container.getBoundingClientRect();
    setSel({
      text,
      x: rect.left - cRect.left + rect.width / 2,
      y: rect.top - cRect.top,
    });
  }, [containerRef]);

  useEffect(() => {
    const onMouseUp = () => window.setTimeout(compute, 0);
    document.addEventListener('mouseup', onMouseUp);
    document.addEventListener('keyup', onMouseUp);
    return () => {
      document.removeEventListener('mouseup', onMouseUp);
      document.removeEventListener('keyup', onMouseUp);
    };
  }, [compute]);

  if (!sel) return null;

  const dismiss = () => {
    window.getSelection()?.removeAllRanges();
    setSel(null);
  };

  return (
    <div
      ref={menuRef}
      className="absolute z-30 -translate-x-1/2 -translate-y-full"
      style={{ left: sel.x, top: sel.y - 8 }}
      onMouseDown={(e) => e.preventDefault()}
    >
      <div className="flex flex-nowrap items-center gap-0.5 rounded-lg border border-border-subtle bg-surface/95 p-1 shadow-lg ring-1 ring-black/[0.04] backdrop-blur dark:ring-white/[0.06]">
        <SelButton
          icon={<Sparkles className="h-3.5 w-3.5" />}
          label={t('pdfReader.selection.explain', { defaultValue: 'Explain' })}
          onClick={() => {
            onExplain(sel.text);
            dismiss();
          }}
        />
        <SelButton
          icon={<Copy className="h-3.5 w-3.5" />}
          label={t('pdfReader.selection.copy', { defaultValue: 'Copy' })}
          onClick={() => {
            onCopy(sel.text);
            dismiss();
          }}
        />
        <SelButton
          icon={<Quote className="h-3.5 w-3.5" />}
          label={t('pdfReader.selection.insert', { defaultValue: 'Quote' })}
          onClick={() => {
            onInsert(sel.text);
            dismiss();
          }}
        />
        <SelButton
          icon={<Languages className="h-3.5 w-3.5" />}
          label={t('pdfReader.selection.translate', { defaultValue: 'Translate' })}
          onClick={() => {
            onTranslate(sel.text);
            dismiss();
          }}
        />
        <SelButton
          icon={<MessageSquarePlus className="h-3.5 w-3.5" />}
          label={t('pdfReader.selection.ask', { defaultValue: 'Ask' })}
          onClick={() => {
            onAsk(sel.text);
            dismiss();
          }}
        />
        <button
          type="button"
          onClick={dismiss}
          className="ml-0.5 shrink-0 rounded p-1 text-muted-foreground hover:bg-surface-sunken hover:text-foreground"
          aria-label={t('common.close', { defaultValue: 'Close' })}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

function SelButton({
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
      className="flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium text-foreground transition-colors hover:bg-surface-sunken"
    >
      {icon}
      {label}
    </button>
  );
}
