import { createContext, useContext, useMemo, useState, type ReactNode, type Ref } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowDown, ArrowRight, ArrowUp, Minus, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { PRIMARY_SOFT_CTA_CLASSNAME } from '@/components/ui/Button';
import type { GenUiNode, GenUiTreeV1 } from '@/types/genUi';
import type { GenUiRenderContextValue } from '@/components/canvas/genUi/GenUiRenderContext';
import { GenUiRenderProvider } from '@/components/canvas/genUi/GenUiRenderContext';
import { GenUiImage } from '@/components/canvas/genUi/GenUiImage';
import { GenUiVideo } from '@/components/canvas/genUi/GenUiVideo';
import { GenUiModel3D } from '@/components/canvas/genUi/GenUiModel3D';
import { GenUiLiveCamera } from '@/components/canvas/genUi/GenUiLiveCamera';
import { GenUiIcon } from '@/components/canvas/genUi/GenUiIcon';
import { GenUiInlineMarkdown, GenUiMarkdown } from '@/components/canvas/genUi/GenUiMarkdown';
import { GenUiChart } from '@/components/canvas/genUi/GenUiChart';
import { GenUiHtmlFrame } from '@/components/canvas/genUi/GenUiHtmlFrame';
import { GenUiThreeJsFrame } from '@/components/canvas/genUi/GenUiThreeJsFrame';
import { IconGlyph } from '@/components/canvas/genUi/IconGlyph';
import { SlideDeckPlayer } from '@/components/canvas/genUi/SlideDeckPlayer';
import {
  renderFeatureGrid,
  renderImageGallery,
  renderKeyValueList,
  renderKpiBoard,
  renderQuoteCard,
  renderSectionHeader,
  renderStepper,
} from '@/components/canvas/genUi/proComponents';
import { renderAspectBox, renderDesignSurface } from '@/components/canvas/genUi/layoutPrimitives';
import {
  composeThemedCardClassName,
  getThemedCardContentClassName,
  type CardSurfaceVariant,
} from '@/components/canvas/genUi/themeManager';
import { dispatchGenUiAction } from '@/lib/genUiActionBus';
import {
  GenUiForm,
  GenUiFormField,
  useGenUiFormExtras,
} from '@/components/canvas/genUi/formComponents';
import {
  BADGE_VARIANTS,
  BUTTON_VARIANTS,
  PROGRESS_COLORS,
  SEVERITY_STYLES,
  TAG_COLORS,
  TEXT_COLORS,
  TEXT_SIZES,
  UI_SLOT_FRAME,
} from '@/components/canvas/genUi/styles';

const s = (v: unknown): string => (typeof v === 'string' ? v : v != null ? String(v) : '');
const b = (v: unknown): boolean => Boolean(v);

function fireGenUiControl(
  p: Record<string, unknown>,
  ctx: GenUiRenderContextValue,
  extra?: { toggled?: boolean; formValues?: Record<string, unknown>; formId?: string },
) {
  const action = p.action;
  const actionId = typeof p.actionId === 'string' ? p.actionId : undefined;
  const base = { sessionId: ctx.sessionId, messageId: ctx.messageId, actionId, ...extra };
  if (action && typeof action === 'object') {
    dispatchGenUiAction(action, base);
  } else if (actionId) {
    dispatchGenUiAction(actionId, base);
  }
}

/** Button that collects enclosing GenUi Form values into its action context. */
function GenUiButtonNode({ node, ctx }: { node: GenUiNode; ctx: GenUiRenderContextValue }) {
  const extras = useGenUiFormExtras();
  const p = node.props ?? {};
  const variant = BUTTON_VARIANTS[(p.variant as string)] || BUTTON_VARIANTS.secondary;
  return (
    <button
      type="button"
      className={cn('px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors', variant)}
      onClick={() => {
        fireGenUiControl(p, ctx, extras);
      }}
    >
      {s(p.label) || 'Action'}
    </button>
  );
}

function GenUiInteractiveButtonNode({ node, ctx }: { node: GenUiNode; ctx: GenUiRenderContextValue }) {
  const extras = useGenUiFormExtras();
  const p = node.props ?? {};
  const variant = BUTTON_VARIANTS[(p.variant as string)] || BUTTON_VARIANTS.primary;
  const sizeClass = p.size === 'lg' ? 'px-5 py-2.5 text-sm' : p.size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-4 py-2 text-sm';
  return (
    <button
      type="button"
      disabled={Boolean(p.disabled)}
      title={p.tooltip as string | undefined}
      className={cn(
        'inline-flex items-center gap-2 font-medium rounded-lg border transition-all',
        sizeClass, variant,
        b(p.disabled) && 'opacity-50 cursor-not-allowed',
      )}
      onClick={() => {
        if (!p.disabled) fireGenUiControl(p, ctx, extras);
      }}
    >
      {!!p.icon && (
        <IconGlyph
          name={p.icon}
          size={16}
          tone="default"
          className="inline-flex shrink-0 items-center leading-none"
        />
      )}
      <span className="leading-none">{s(p.label) || 'Action'}</span>
    </button>
  );
}

function GenUiToggleButtonNode({ node, ctx }: { node: GenUiNode; ctx: GenUiRenderContextValue }) {
  const extras = useGenUiFormExtras();
  const p = node.props ?? {};
  const active = Boolean(p.active);
  return (
    <button
      type="button"
      className={cn(
        'px-3 py-1.5 text-xs font-medium rounded-lg border transition-all',
        active
          ? cn(
              PRIMARY_SOFT_CTA_CLASSNAME,
              'border-primary-300 dark:border-primary-600',
            )
          : 'bg-surface text-foreground border-border hover:bg-surface-sunken',
      )}
      onClick={() => {
        fireGenUiControl(p, ctx, { ...extras, toggled: !active });
      }}
    >
      {s(p.label) || 'Toggle'}
    </button>
  );
}

function UnknownNode({ node }: { node: GenUiNode }) {
  return (
    <div className="rounded-lg border border-border p-2 text-xs text-muted-foreground font-mono">
      Unknown kind: {String(node.kind)}
    </div>
  );
}

function TabsContainer({
  node,
  depth,
  ctx,
}: {
  node: GenUiNode;
  depth: number;
  ctx: GenUiRenderContextValue;
}) {
  const ch = (node.children || []) as GenUiNode[];
  const tabs = ch.filter((c) => c.kind === 'TabItem');
  const defaultTab = (node.props?.defaultTab as string) || (tabs[0]?.props?.label as string) || '';
  const [active, setActive] = useState(defaultTab);
  const activeTab = tabs.find((t) => (t.props?.label as string) === active) || tabs[0];

  return (
    <div key={node.nodeId}>
      <div className="flex gap-1 border-b border-border mb-2">
        {tabs.map((t) => {
          const label = (t.props?.label as string) || 'Tab';
          return (
            <button
              key={t.nodeId}
              type="button"
              onClick={() => setActive(label)}
              className={cn(
                'px-3 py-1.5 text-xs font-medium rounded-t-lg transition-colors',
                (activeTab?.nodeId === t.nodeId)
                  ? 'bg-surface-elevated text-foreground border-b-2 border-primary-500'
                  : 'text-muted-foreground hover:text-foreground hover:bg-surface-sunken',
              )}
            >
              {label}
            </button>
          );
        })}
      </div>
      {activeTab && (
        <div>
          {(activeTab.children || []).map((c: GenUiNode) => (
            <div key={c.nodeId}>{renderNode(c, depth + 1, ctx)}</div>
          ))}
        </div>
      )}
    </div>
  );
}

function AccordionContainer({
  node,
  depth,
  ctx,
}: {
  node: GenUiNode;
  depth: number;
  ctx: GenUiRenderContextValue;
}) {
  const ch = (node.children || []) as GenUiNode[];
  return (
    <div key={node.nodeId} className="space-y-1">
      {ch.filter((c) => c.kind === 'AccordionItem').map((item) => (
        <AccordionItemRenderer key={item.nodeId} node={item} depth={depth} ctx={ctx} />
      ))}
    </div>
  );
}

type ListVariantKind = 'default' | 'separated' | 'bordered';

interface ListRenderContextValue {
  variant: ListVariantKind;
  ordered: boolean;
  indexOf: (nodeId: string) => number | undefined;
}

const ListRenderContext = createContext<ListRenderContextValue | null>(null);

function ListItemRenderer({ node }: { node: GenUiNode }) {
  const p = (node.props || {}) as Record<string, unknown>;
  const listCtx = useContext(ListRenderContext);
  const icon = p.icon as string | undefined;
  const value = s(p.value);
  const variant: ListVariantKind = listCtx?.variant ?? 'default';
  const ordered = !!listCtx?.ordered;
  const baseText = 'text-sm leading-6 text-foreground';
  const valueSpan = (
    <span className="min-w-0 flex-1 break-words [overflow-wrap:anywhere]">
      <GenUiInlineMarkdown value={value} />
    </span>
  );

  if (variant === 'separated' || variant === 'bordered') {
    let leading: ReactNode;
    if (icon) {
      leading = (
        <span className="mt-0.5 inline-flex shrink-0">
          <IconGlyph name={icon} size={16} tone={s(p.iconTone) || 'muted'} />
        </span>
      );
    } else if (ordered) {
      const idx = listCtx?.indexOf(node.nodeId);
      leading = idx ? (
        <span className="mt-[1px] inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-sunken text-[10px] font-semibold text-muted-foreground tabular-nums">
          {idx}
        </span>
      ) : null;
    } else {
      leading = (
        <span
          aria-hidden
          className="mt-[9px] h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/60"
        />
      );
    }
    return (
      <div className={cn('flex items-start gap-2.5', baseText)}>
        {leading}
        {valueSpan}
      </div>
    );
  }

  // Default variant: keep semantic <li> inside the <ul>/<ol>.
  if (icon) {
    // Hide the default marker; let the icon act as the bullet and align flush
    // with non-iconed siblings (which sit at the same x-position thanks to the
    // ``-ml-5`` compensation against the parent ``pl-5``).
    return (
      <li className={cn('list-none -ml-5 flex items-start gap-2', baseText)}>
        <span className="mt-0.5 inline-flex shrink-0">
          <IconGlyph name={icon} size={16} tone={s(p.iconTone) || 'muted'} />
        </span>
        {valueSpan}
      </li>
    );
  }
  return (
    <li className={cn(baseText, 'pl-1 marker:text-muted-foreground/70')}>
      <span className="break-words [overflow-wrap:anywhere]">{value}</span>
    </li>
  );
}

function AccordionItemRenderer({
  node,
  depth,
  ctx,
}: {
  node: GenUiNode;
  depth: number;
  ctx: GenUiRenderContextValue;
}) {
  const p = (node.props || {}) as Record<string, unknown>;
  const [open, setOpen] = useState(Boolean(p.defaultOpen));
  const ch = (node.children || []) as GenUiNode[];

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-foreground hover:bg-surface-sunken transition-colors"
      >
        <span>{String(p.title || 'Section')}</span>
        <span className={cn('text-xs transition-transform', open && 'rotate-180')}>▼</span>
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-1">
          {ch.map((c) => <div key={c.nodeId}>{renderNode(c, depth + 1, ctx)}</div>)}
        </div>
      )}
    </div>
  );
}

function renderNode(node: GenUiNode, depth: number, ctx: GenUiRenderContextValue = {}): ReactNode {
  const k = (node.kind || '') as string;
  const p = (node.props || {}) as Record<string, unknown>;
  const ch = (node.children || []) as GenUiNode[];

  switch (k) {
    // ── Layout ─────────────────────────────────────────────────────────
    case 'Stack':
      return (
        <div
          key={node.nodeId}
          className={cn('flex flex-col', depth ? 'mt-1' : '')}
          style={{
            gap: (p.gap as number) || 8,
            padding: p.padding ? `${p.padding as number}px` : undefined,
            alignItems: p.align === 'center' ? 'center' : p.align === 'end' ? 'flex-end' : undefined,
          }}
        >
          {ch.map((c) => <div key={c.nodeId}>{renderNode(c, depth + 1, ctx)}</div>)}
        </div>
      );

    case 'Grid': {
      const cols = Math.min(6, Math.max(1, (p.columns as number) || 2));
      return (
        <div
          key={node.nodeId}
          className="grid"
          style={{
            gridTemplateColumns: p.minChildWidth
              ? `repeat(auto-fill, minmax(${p.minChildWidth as string}, 1fr))`
              : `repeat(${cols}, minmax(0, 1fr))`,
            gap: `${(p.gap as number) || 12}px`,
          }}
        >
          {ch.map((c) => <div key={c.nodeId}>{renderNode(c, depth + 1, ctx)}</div>)}
        </div>
      );
    }

    case 'Row':
      return (
        <div
          key={node.nodeId}
          className="flex flex-wrap items-center"
          style={{
            gap: `${(p.gap as number) || 8}px`,
            alignItems: p.align === 'start' ? 'flex-start' : p.align === 'end' ? 'flex-end' : p.align === 'stretch' ? 'stretch' : 'center',
            justifyContent: p.justify === 'end' ? 'flex-end' : p.justify === 'center' ? 'center' : p.justify === 'between' ? 'space-between' : p.justify === 'around' ? 'space-around' : 'flex-start',
          }}
        >
          {ch.map((c) => <div key={c.nodeId}>{renderNode(c, depth + 1, ctx)}</div>)}
        </div>
      );

    case 'Spacer':
      return <div key={node.nodeId} style={{ height: `${(p.size as number) || 16}px` }} />;

    case 'ScrollArea':
      return (
        <div key={node.nodeId} className="overflow-auto" style={{ maxHeight: `${(p.maxHeight as number) || 300}px` }}>
          {ch.map((c) => <div key={c.nodeId}>{renderNode(c, depth + 1, ctx)}</div>)}
        </div>
      );

    case 'Tabs':
      return <TabsContainer key={node.nodeId} node={node} depth={depth} ctx={ctx} />;

    case 'TabItem':
      return (
        <div key={node.nodeId}>
          {ch.map((c) => <div key={c.nodeId}>{renderNode(c, depth + 1, ctx)}</div>)}
        </div>
      );

    case 'Accordion':
      return <AccordionContainer key={node.nodeId} node={node} depth={depth} ctx={ctx} />;

    case 'AccordionItem':
      return <AccordionItemRenderer key={node.nodeId} node={node} depth={depth} ctx={ctx} />;

    case 'AspectBox':
      return renderAspectBox(node, depth, (c, d) => renderNode(c, d, ctx));

    case 'DesignSurface':
      return renderDesignSurface(node, depth, (c, d, childCtx) => renderNode(c, d, childCtx), ctx);

    // ── Typography & basic ─────────────────────────────────────────────
    case 'Text': {
      const v = (p.value as string) || '';
      const sizeClass = TEXT_SIZES[(p.size as string)] || 'text-sm';
      const colorClass = TEXT_COLORS[(p.color as string)] || 'text-foreground';
      return (
        <p key={node.nodeId} className={cn(sizeClass, colorClass, b(p.bold) && 'font-semibold')}>
          <GenUiInlineMarkdown value={v} />
        </p>
      );
    }

    case 'Heading': {
      const level = Math.min(4, Math.max(1, (p.level as number) || 2));
      const v = (p.value as string) || '';
      const sizes = ['text-2xl', 'text-xl', 'text-lg', 'text-base'];
      const Tag = (`h${level}` as 'h1' | 'h2' | 'h3' | 'h4');
      return <Tag key={node.nodeId} className={cn('font-semibold text-foreground', sizes[level - 1])}>{v}</Tag>;
    }

    case 'Divider': {
      const label = p.label as string | undefined;
      if (label) {
        return (
          <div key={node.nodeId} className="flex items-center gap-3 my-3">
            <div className="flex-1 h-px bg-border" />
            <span className="text-xs text-muted-foreground">{label}</span>
            <div className="flex-1 h-px bg-border" />
          </div>
        );
      }
      return <hr key={node.nodeId} className="border-border my-3" />;
    }

    case 'Skeleton': {
      const n = (p.lines as number) || 2;
      if (p.variant === 'avatar') {
        return (
          <div key={node.nodeId} className="flex items-center gap-3 animate-pulse">
            <div className="w-10 h-10 rounded-full bg-surface-sunken" />
            <div className="flex-1 space-y-2">
              <div className="h-3 bg-surface-sunken rounded w-1/3" />
              <div className="h-3 bg-surface-sunken rounded w-1/2" />
            </div>
          </div>
        );
      }
      if (p.variant === 'card') {
        return (
          <div key={node.nodeId} className="rounded-xl border border-border p-4 space-y-3 animate-pulse">
            <div className="h-4 bg-surface-sunken rounded w-2/3" />
            <div className="h-3 bg-surface-sunken rounded w-full" />
            <div className="h-3 bg-surface-sunken rounded w-4/5" />
          </div>
        );
      }
      return (
        <div key={node.nodeId} className="space-y-2 animate-pulse">
          {Array.from({ length: n }).map((_, i) => (
            <div key={i} className="h-3 bg-surface-sunken rounded" style={{ width: `${70 + Math.random() * 30}%` }} />
          ))}
        </div>
      );
    }

    // ── Data display ───────────────────────────────────────────────────
    case 'Badge': {
      const variant = BADGE_VARIANTS[(p.variant as string)] || BADGE_VARIANTS.default;
      return (
        <span key={node.nodeId} className={cn('inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium', variant)}>
          {s(p.value)}
        </span>
      );
    }

    case 'Tag': {
      const color = TAG_COLORS[(p.color as string)] || TAG_COLORS.gray;
      return (
        <span key={node.nodeId} className={cn('inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium', color)}>
          {s(p.label)}
        </span>
      );
    }

    case 'Stat': {
      const trend = p.trend as string;
      const trendColor =
        trend === 'up'
          ? 'text-mint-600 dark:text-mint-400'
          : trend === 'down'
            ? 'text-rose-600 dark:text-rose-400'
            : 'text-muted-foreground';
      const TrendGlyph =
        trend === 'up' ? ArrowUp : trend === 'down' ? ArrowDown : Minus;
      return (
        <div key={node.nodeId} className="flex flex-col gap-1">
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            {!!p.icon && <IconGlyph name={p.icon} size={14} tone="muted" />}
            {s(p.label)}
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-foreground">{s(p.value)}</span>
            {!!p.delta && (
              <span className={cn('inline-flex items-center gap-0.5 text-sm font-medium', trendColor)}>
                <TrendGlyph className="h-3.5 w-3.5" aria-hidden />
                {s(p.delta)}
              </span>
            )}
          </div>
        </div>
      );
    }

    case 'Progress': {
      const val = Math.min(100, Math.max(0, (p.value as number) || 0));
      const color = PROGRESS_COLORS[(p.color as string)] || PROGRESS_COLORS.primary;
      return (
        <div key={node.nodeId} className="space-y-1">
          {!!p.label && (
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">{s(p.label)}</span>
              <span className="text-foreground font-medium">{val}%</span>
            </div>
          )}
          <div className="h-2 bg-surface-sunken rounded-full overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all duration-500', color)}
              style={{ width: `${val}%` }}
            />
          </div>
        </div>
      );
    }

    case 'Avatar': {
      const size = p.size === 'lg' ? 'w-14 h-14 text-lg' : p.size === 'sm' ? 'w-8 h-8 text-xs' : 'w-10 h-10 text-sm';
      const name = (p.name as string) || '';
      const initials = name.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase();
      if (p.src) {
        return <img key={node.nodeId} src={p.src as string} alt={name} className={cn('rounded-full object-cover', size)} />;
      }
      return (
        <div key={node.nodeId} className={cn('rounded-full bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 flex items-center justify-center font-semibold', size)}>
          {initials || '?'}
        </div>
      );
    }

    case 'Image':
      return <GenUiImage key={node.nodeId} node={node} />;

    case 'Video':
      return <GenUiVideo key={node.nodeId} node={node} />;

    case 'Model3D':
      return <GenUiModel3D key={node.nodeId} node={node} />;

    case 'LiveCamera':
      return <GenUiLiveCamera key={node.nodeId} node={node} />;

    case 'Icon':
      return <GenUiIcon key={node.nodeId} node={node} />;

    case 'Table': {
      const headers = (p.headers as string[]) || [];
      return (
        <div
          key={node.nodeId}
          className="min-w-0 max-w-full overflow-x-auto rounded-lg border border-border no-scrollbar"
        >
          <table className={cn('w-full min-w-0 text-sm', b(p.compact) && 'text-xs')}>
            {headers.length > 0 && (
              <thead>
                <tr className="bg-surface-sunken">
                  {headers.map((h, i) => (
                    <th
                      key={i}
                      className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider break-words [overflow-wrap:anywhere]"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody className={cn(b(p.striped) && '[&>tr:nth-child(even)]:bg-surface-sunken/50')}>
              {ch.map((c) => renderNode(c, depth + 1, ctx))}
            </tbody>
          </table>
        </div>
      );
    }

    case 'TableRow': {
      return (
        <tr key={node.nodeId} className={cn('border-t border-border', b(p.highlight) && 'bg-primary-50/50 dark:bg-primary-950/20')}>
          {ch.map((c) => renderNode(c, depth + 1, ctx))}
        </tr>
      );
    }

    case 'TableCell': {
      const align = p.align === 'center' ? 'text-center' : p.align === 'right' ? 'text-right' : 'text-left';
      return (
        <td
          key={node.nodeId}
          className={cn('px-3 py-2 text-foreground break-words [overflow-wrap:anywhere]', align, b(p.bold) && 'font-semibold')}
        >
          <GenUiInlineMarkdown value={p.value} />
          {ch.length > 0 && ch.map((c) => <span key={c.nodeId}>{renderNode(c, depth + 1, ctx)}</span>)}
        </td>
      );
    }

    case 'List': {
      const ordered = b(p.ordered);
      const rawVariant = s(p.variant);
      const variant: ListVariantKind =
        rawVariant === 'separated' || rawVariant === 'bordered' ? rawVariant : 'default';

      const indexMap = new Map<string, number>();
      let counter = 0;
      for (const c of ch) {
        if (c.kind === 'ListItem') {
          counter += 1;
          indexMap.set(c.nodeId, counter);
        }
      }
      const ctxValue: ListRenderContextValue = {
        variant,
        ordered,
        indexOf: (id) => indexMap.get(id),
      };

      if (variant === 'separated') {
        return (
          <ListRenderContext.Provider key={node.nodeId} value={ctxValue}>
            <div className="divide-y divide-border/70">
              {ch.map((c) => (
                <div key={c.nodeId} className="py-1.5 first:pt-0 last:pb-0">
                  {renderNode(c, depth + 1, ctx)}
                </div>
              ))}
            </div>
          </ListRenderContext.Provider>
        );
      }
      if (variant === 'bordered') {
        return (
          <ListRenderContext.Provider key={node.nodeId} value={ctxValue}>
            <div className="overflow-hidden rounded-lg border border-border bg-surface-elevated/40 divide-y divide-border/70">
              {ch.map((c) => (
                <div key={c.nodeId} className="px-3 py-2">
                  {renderNode(c, depth + 1, ctx)}
                </div>
              ))}
            </div>
          </ListRenderContext.Provider>
        );
      }
      const Tag = ordered ? 'ol' : 'ul';
      const listStyle = ordered ? 'list-decimal' : 'list-disc';
      return (
        <ListRenderContext.Provider key={node.nodeId} value={ctxValue}>
          <Tag className={cn('space-y-1 pl-5 marker:text-muted-foreground/70', listStyle)}>
            {ch.map((c) => renderNode(c, depth + 1, ctx))}
          </Tag>
        </ListRenderContext.Provider>
      );
    }

    case 'ListItem':
      return <ListItemRenderer key={node.nodeId} node={node} />;

    case 'CodeBlock':
      return (
        <div key={node.nodeId} className="rounded-lg overflow-hidden border border-border">
          {!!p.title && (
            <div className="px-3 py-1.5 bg-surface-sunken text-xs font-medium text-muted-foreground border-b border-border flex items-center gap-2">
              {!!p.language && <span className="text-[10px] uppercase tracking-wider opacity-60">{s(p.language)}</span>}
              <span>{s(p.title)}</span>
            </div>
          )}
          <pre className="p-3 bg-surface-sunken/60 text-xs overflow-auto font-mono text-foreground">
            <code>{s(p.code)}</code>
          </pre>
        </div>
      );

    case 'Markdown':
      return <GenUiMarkdown key={node.nodeId} node={node} />;

    case 'Chart':
      return <GenUiChart key={node.nodeId} node={node} />;

    // ── Rich Cards ─────────────────────────────────────────────────────
    case 'Card': {
      const padClass = p.padding === 'sm' ? 'p-3' : p.padding === 'lg' ? 'p-6' : 'p-4';
      const variantKey = ((p.variant as string) || 'default') as CardSurfaceVariant;
      const surface = composeThemedCardClassName(ctx.themeId, variantKey);
      const themedContent = getThemedCardContentClassName(ctx.themeId);
      return (
        <div key={node.nodeId} className={cn(surface, padClass, themedContent)}>
          {(!!p.eyebrow || !!p.icon || !!p.title || !!p.subtitle) && (
            <div className="mb-3 flex items-start gap-3">
              {!!p.icon && <IconGlyph name={p.icon} size={22} tone={s(p.iconTone) || 'primary'} />}
              <div className="min-w-0">
                {!!p.eyebrow && (
                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-primary-600 dark:text-primary-300">
                    {s(p.eyebrow)}
                  </p>
                )}
                {!!p.title && <div className="text-sm font-semibold text-foreground">{s(p.title)}</div>}
                {!!p.subtitle && (
                  <div className="text-xs text-muted-foreground mt-0.5">{s(p.subtitle)}</div>
                )}
              </div>
            </div>
          )}
          <div className="space-y-1">{ch.map((c) => <div key={c.nodeId}>{renderNode(c, depth + 1, ctx)}</div>)}</div>
        </div>
      );
    }

    case 'WeatherCard': {
      const forecast = (p.forecast as Array<{ day: string; high: string; low: string; icon: string }>) || [];
      return (
        <div key={node.nodeId} className="rounded-2xl overflow-hidden bg-gradient-to-br from-primary-500 to-primary-700 text-white shadow-lg">
          <div className="p-5">
            <div className="flex justify-between items-start">
              <div>
                <p className="text-sm opacity-80 font-medium">{s(p.location)}</p>
                <p className="text-5xl font-bold mt-1 tracking-tight">{s(p.temperature)}</p>
                <p className="text-sm mt-1 opacity-90">{s(p.condition)}</p>
              </div>
              <span className="flex h-14 w-14 items-center justify-center shrink-0 [&_svg]:text-white">
                <IconGlyph name={p.icon ?? 'sun'} size={52} tone="default" />
              </span>
            </div>
            <div className="flex gap-4 mt-5 text-sm opacity-90">
              {!!p.humidity && <span>💧 {s(p.humidity)}</span>}
              {!!p.wind && <span>🌬️ {s(p.wind)}</span>}
              {!!p.feelsLike && <span>🌡️ {s(p.feelsLike)}</span>}
            </div>
          </div>
          {forecast.length > 0 && (
            <div className="px-5 py-3 bg-white/10 backdrop-blur-sm flex gap-3 overflow-auto">
              {forecast.map((f, i) => (
                <div key={i} className="flex flex-col items-center min-w-[56px] text-xs">
                  <span className="opacity-70">{f.day}</span>
                  <span className="text-lg my-0.5">{f.icon || '☀️'}</span>
                  <span className="font-medium">{f.high}</span>
                  <span className="opacity-60">{f.low}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      );
    }

    case 'DataCard':
      return (
        <div
          key={node.nodeId}
          className={cn(composeThemedCardClassName(ctx.themeId, 'default'), 'p-4', getThemedCardContentClassName(ctx.themeId))}
        >
          <div className="flex items-start gap-3">
            {!!p.icon && (
              <span className="inline-flex shrink-0">
                <IconGlyph name={p.icon} size={28} tone={s(p.iconTone) || 'primary'} />
              </span>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-xs text-muted-foreground font-medium">{s(p.title)}</p>
              <p className="text-xl font-bold text-foreground mt-0.5">{s(p.value)}</p>
              {!!p.description && <p className="text-xs text-muted-foreground mt-1">{s(p.description)}</p>}
            </div>
          </div>
          {ch.length > 0 && (
            <div className="mt-3 space-y-1">
              {ch.map((c) => <div key={c.nodeId}>{renderNode(c, depth + 1, ctx)}</div>)}
            </div>
          )}
        </div>
      );

    case 'MetricCard': {
      const trend = p.trend as string;
      const trendBg =
        trend === 'up'
          ? 'bg-mint-100 text-mint-800 dark:bg-mint-900/30 dark:text-mint-300'
          : trend === 'down'
            ? 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300'
            : 'bg-surface-sunken text-muted-foreground dark:bg-surface-sunken';
      const TrendIc = trend === 'up' ? ArrowUp : trend === 'down' ? ArrowDown : ArrowRight;
      return (
        <div
          key={node.nodeId}
          className={cn(composeThemedCardClassName(ctx.themeId, 'default'), 'p-4', getThemedCardContentClassName(ctx.themeId))}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">{s(p.title)}</span>
            {!!p.icon && (
              <span className="inline-flex">
                <IconGlyph name={p.icon} size={22} tone={s(p.iconTone) || 'muted'} />
              </span>
            )}
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-foreground">{s(p.value)}</span>
            {!!p.delta && (
              <span className={cn('inline-flex items-center gap-0.5 text-xs font-semibold px-1.5 py-0.5 rounded-full', trendBg)}>
                <TrendIc className="h-3 w-3" aria-hidden />
                {s(p.delta)}
              </span>
            )}
          </div>
          {!!p.period && <p className="text-[11px] text-muted-foreground mt-1">{s(p.period)}</p>}
        </div>
      );
    }

    case 'ProfileCard': {
      const stats = (p.stats as Array<{ label: string; value: string }>) || [];
      const initials = ((p.name as string) || '').split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase();
      return (
        <div
          key={node.nodeId}
          className={cn(
            composeThemedCardClassName(ctx.themeId, 'default'),
            'p-5 text-center',
            getThemedCardContentClassName(ctx.themeId),
          )}
        >
          {p.avatarUrl ? (
            <img src={s(p.avatarUrl)} alt={s(p.name)} className="w-16 h-16 rounded-full mx-auto object-cover" />
          ) : (
            <div className="w-16 h-16 rounded-full mx-auto bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 flex items-center justify-center text-xl font-bold">
              {initials || '?'}
            </div>
          )}
          <h3 className="font-semibold text-foreground mt-3">{s(p.name)}</h3>
          {!!p.role && <p className="text-xs text-muted-foreground mt-0.5">{s(p.role)}</p>}
          {!!p.bio && <p className="text-sm text-muted-foreground mt-2">{s(p.bio)}</p>}
          {stats.length > 0 && (
            <div className="flex justify-center gap-6 mt-4 pt-4 border-t border-border">
              {stats.map((row, i) => (
                <div key={i} className="text-center">
                  <div className="text-lg font-bold text-foreground">{row.value}</div>
                  <div className="text-[11px] text-muted-foreground">{row.label}</div>
                </div>
              ))}
            </div>
          )}
          {ch.length > 0 && (
            <div className="mt-3 flex justify-center gap-2">
              {ch.map((c) => <span key={c.nodeId}>{renderNode(c, depth + 1, ctx)}</span>)}
            </div>
          )}
        </div>
      );
    }

    case 'MediaCard': {
      const ratio = p.aspectRatio === '1/1' ? 'aspect-square' : p.aspectRatio === '4/3' ? 'aspect-[4/3]' : 'aspect-video';
      return (
        <div key={node.nodeId} className="rounded-xl border border-border bg-surface-elevated overflow-hidden">
          {!!p.imageUrl && (
            <div className="relative">
              <img src={s(p.imageUrl)} alt={s(p.title)} className={cn('w-full object-cover', ratio)} />
              {!!p.badge && (
                <span className="absolute top-2 right-2 px-2 py-0.5 bg-black/60 text-white rounded-full text-xs font-medium backdrop-blur-sm">
                  {s(p.badge)}
                </span>
              )}
            </div>
          )}
          <div className="p-4">
            {!!p.title && (
              <h3 className="flex items-center gap-2 font-semibold text-foreground">
                {!!p.icon && <IconGlyph name={p.icon} size={18} tone={s(p.iconTone) || 'primary'} />}
                {s(p.title)}
              </h3>
            )}
            {!!p.description && <p className="text-sm text-muted-foreground mt-1">{s(p.description)}</p>}
            {ch.length > 0 && (
              <div className="mt-3 flex gap-2">
                {ch.map((c) => <span key={c.nodeId}>{renderNode(c, depth + 1, ctx)}</span>)}
              </div>
            )}
          </div>
        </div>
      );
    }

    case 'AlertCard': {
      const sev = (SEVERITY_STYLES[s(p.severity)] ?? SEVERITY_STYLES.info)!;
      const ic = p.icon != null && String(p.icon).trim() !== '' ? p.icon : sev.icon;
      return (
        <div key={node.nodeId} className={cn('rounded-xl border p-4', sev.bg, sev.border)}>
          <div className="flex items-start gap-3">
            <span className={cn('flex-shrink-0 inline-flex', sev.text)}>
              <IconGlyph name={ic} size={22} tone="default" />
            </span>
            <div className="flex-1 min-w-0">
              {!!p.title && <h4 className={cn('font-semibold text-sm', sev.text)}>{s(p.title)}</h4>}
              {!!p.message && <p className={cn('text-sm mt-0.5 opacity-90', sev.text)}>{s(p.message)}</p>}
            </div>
          </div>
        </div>
      );
    }

    case 'TimelineCard': {
      const events = (p.events as Array<{ time: string; title: string; description?: string; icon?: string; status?: string }>) || [];
      return (
        <div key={node.nodeId} className="rounded-xl border border-border bg-surface-elevated p-4">
          {!!p.title && <h3 className="font-semibold text-foreground mb-4">{s(p.title)}</h3>}
          <div className="relative space-y-4 pl-6">
            <div className="absolute left-[9px] top-2 bottom-2 w-px bg-border" />
            {events.map((e, i) => (
              <div key={i} className="relative">
                <div className="absolute -left-6 top-0.5 w-[18px] h-[18px] rounded-full bg-surface-elevated border-2 border-primary-500 flex items-center justify-center text-[10px]">
                  {e.icon || '●'}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-foreground">{e.title}</span>
                    {e.status && <span className="text-[10px] text-muted-foreground">{e.status}</span>}
                  </div>
                  {e.time && <span className="text-[11px] text-muted-foreground">{e.time}</span>}
                  {e.description && <p className="text-xs text-muted-foreground mt-0.5">{e.description}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      );
    }

    // ── Interactive ─────────────────────────────────────────────────────
    case 'Button':
      return <GenUiButtonNode key={node.nodeId} node={node} ctx={ctx} />;

    case 'InteractiveButton':
      return <GenUiInteractiveButtonNode key={node.nodeId} node={node} ctx={ctx} />;

    case 'ToggleButton':
      return <GenUiToggleButtonNode key={node.nodeId} node={node} ctx={ctx} />;

    case 'LinkButton':
      return (
        <a
          key={node.nodeId}
          href={p.url as string || '#'}
          target={b(p.external) ? '_blank' : undefined}
          rel={b(p.external) ? 'noopener noreferrer' : undefined}
          className="inline-flex items-center gap-1 text-sm text-primary-600 dark:text-primary-400 hover:underline font-medium"
        >
          {s(p.label) || 'Link'}
          {b(p.external) && <span className="text-[10px]">↗</span>}
        </a>
      );

    case 'Input':
    case 'Select':
    case 'NumberInput':
    case 'Switch':
    case 'Slider':
    case 'FileInput':
    case 'Textarea':
      return <GenUiFormField key={node.nodeId} node={node} />;

    case 'Form':
      return (
        <GenUiForm key={node.nodeId} node={node} ctx={ctx}>
          {ch.map((c) => (
            <div key={c.nodeId}>{renderNode(c, depth + 1, ctx)}</div>
          ))}
        </GenUiForm>
      );

    case 'Chip': {
      const selected = Boolean(p.selected);
      const chipColor = p.color ? TAG_COLORS[(p.color as string)] || '' : '';
      return (
        <span
          key={node.nodeId}
          className={cn(
            'inline-flex items-center px-3 py-1 rounded-full text-xs font-medium cursor-default transition-colors',
            selected
              ? PRIMARY_SOFT_CTA_CLASSNAME
              : chipColor || 'bg-surface-sunken text-foreground hover:bg-border-subtle dark:hover:bg-surface-elevated',
          )}
        >
          {s(p.label)}
        </span>
      );
    }

    case 'ChipGroup':
      return (
        <div key={node.nodeId} className="space-y-1">
          {!!p.label && <span className="text-xs font-medium text-muted-foreground">{s(p.label)}</span>}
          <div className="flex flex-wrap gap-2">
            {ch.map((c) => <span key={c.nodeId}>{renderNode(c, depth + 1, ctx)}</span>)}
          </div>
        </div>
      );

    // ── Feedback ───────────────────────────────────────────────────────
    case 'Alert': {
      const sev = (SEVERITY_STYLES[s(p.severity)] ?? SEVERITY_STYLES.info)!;
      const ic = p.icon != null && String(p.icon).trim() !== '' ? p.icon : sev.icon;
      return (
        <div key={node.nodeId} className={cn('rounded-lg border px-4 py-3 flex items-start gap-3', sev.bg, sev.border)}>
          <span className={cn('flex-shrink-0 mt-0.5 inline-flex', sev.text)}>
            <IconGlyph name={ic} size={18} tone="default" />
          </span>
          <div className="flex-1 min-w-0">
            {!!p.title && <div className={cn('text-sm font-semibold', sev.text)}>{s(p.title)}</div>}
            {!!p.message && <div className={cn('text-sm', sev.text, b(p.title) && 'mt-0.5')}>{s(p.message)}</div>}
          </div>
        </div>
      );
    }

    case 'Callout': {
      const variantMap: Record<string, { bg: string; border: string; icon: string }> = {
        info: { bg: 'bg-blue-50/80 dark:bg-blue-950/20', border: 'border-l-4 border-l-blue-500', icon: 'ℹ️' },
        tip: { bg: 'bg-green-50/80 dark:bg-green-950/20', border: 'border-l-4 border-l-green-500', icon: '💡' },
        warning: { bg: 'bg-yellow-50/80 dark:bg-yellow-950/20', border: 'border-l-4 border-l-yellow-500', icon: '⚠️' },
        important: { bg: 'bg-purple-50/80 dark:bg-purple-950/20', border: 'border-l-4 border-l-purple-500', icon: '⭐' },
      };
      const cv = (variantMap[s(p.variant)] ?? variantMap.info)!;
      return (
        <div key={node.nodeId} className={cn('rounded-lg px-4 py-3', cv.bg, cv.border)}>
          <div className="flex items-start gap-2">
            <span className="text-sm">{cv.icon}</span>
            <div>
              {!!p.title && <div className="text-sm font-semibold text-foreground">{s(p.title)}</div>}
              {!!p.message && <div className="text-sm text-foreground/80 mt-0.5">{s(p.message)}</div>}
            </div>
          </div>
        </div>
      );
    }

    // ── Embed ──────────────────────────────────────────────────────────
    case 'HostedCanvasFrame': {
      const id = p.canvasId as string | undefined;
      if (!id) return <UnknownNode node={node} />;
      return (
        <div
          key={node.nodeId}
          className="text-xs text-muted-foreground p-2 border border-dashed border-border rounded-lg"
        >
          Canvas embed: {id} (use HTML preview tab for interactive view)
        </div>
      );
    }

    case 'HtmlFrame':
      return <GenUiHtmlFrame key={node.nodeId} node={node} />;

    case 'ThreeJsFrame':
      return <GenUiThreeJsFrame key={node.nodeId} node={node} />;

    case 'JsonDebug':
      return (
        <pre key={node.nodeId} className="text-xs overflow-auto max-h-40 bg-surface-sunken p-3 rounded-lg font-mono">
          {p.data ? JSON.stringify(p.data, null, 2) : s(p.label) || 'data'}
        </pre>
      );

    case 'SlideDeck':
      return (
        <SlideDeckPlayer
          key={node.nodeId}
          node={node}
          depth={depth}
          ctx={ctx}
          renderNode={renderNode}
        />
      );

    case 'Slide': {
      const layout =
        (p.layout as string) ||
        (String(p.variant || '').toLowerCase() === 'cover'
          ? 'cover'
          : String(p.variant || '').toLowerCase() === 'two-column'
            ? 'two-column'
            : 'title-content');
      const bg =
        p.background === 'primary'
          ? 'bg-gradient-to-br from-primary-600 to-primary-800 text-white'
          : p.background === 'gradient'
            ? 'bg-gradient-to-br from-surface-elevated via-primary-50/40 to-surface-elevated dark:via-primary-950/25'
            : p.background === 'image' && typeof p.imageUrl === 'string'
              ? 'relative overflow-hidden bg-surface-elevated'
              : 'bg-surface-elevated text-foreground border border-border';
      const ink = p.background === 'primary' ? 'text-white' : 'text-foreground';
      const mutedInk = p.background === 'primary' ? 'text-white/85' : 'text-muted-foreground';
      return (
        <div key={node.nodeId} className={cn('relative flex h-full min-h-0 flex-col rounded-xl', bg)}>
          {p.background === 'image' && typeof p.imageUrl === 'string' && (
            <img
              src={p.imageUrl}
              alt=""
              className="pointer-events-none absolute inset-0 h-full w-full object-cover opacity-35"
            />
          )}
          <div
            className={cn(
              'relative z-[1] flex min-h-0 flex-1 flex-col gap-4 p-1',
              layout === 'two-column' && 'md:flex-row md:items-start md:gap-8',
              layout === 'cover' && 'items-center justify-center text-center',
            )}
          >
            {(!!p.eyebrow || !!p.title || !!p.subtitle) && (
              <header
                className={cn(
                  'shrink-0 space-y-1',
                  layout === 'two-column' && 'md:w-[38%]',
                  layout === 'cover' && 'space-y-3',
                )}
              >
                {!!p.eyebrow && (
                  <p className={cn('text-[10px] font-semibold uppercase tracking-[0.14em]', mutedInk, 'opacity-90')}>
                    {s(p.eyebrow)}
                  </p>
                )}
                {!!p.title && (
                  <h2 className={cn('text-2xl font-bold leading-tight sm:text-3xl', ink)}>
                    {s(p.title)}
                  </h2>
                )}
                {!!p.subtitle && <p className={cn('text-sm', mutedInk)}>{s(p.subtitle)}</p>}
              </header>
            )}
            <div
              className={cn(
                'min-h-0 flex-1 space-y-2 overflow-auto',
                layout === 'two-column' && 'md:w-[62%]',
                layout === 'cover' && 'w-full max-w-prose',
              )}
            >
              {ch.map((c) => (
                <div key={c.nodeId}>{renderNode(c, depth + 1, ctx)}</div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    case 'SectionHeader':
      return renderSectionHeader({ node, depth, renderChild: (c, d) => renderNode(c, d, ctx) });

    case 'KpiBoard':
      return renderKpiBoard({ node, depth, renderChild: (c, d) => renderNode(c, d, ctx) });

    case 'FeatureGrid':
      return renderFeatureGrid({ node, depth, renderChild: (c, d) => renderNode(c, d, ctx) });

    case 'Stepper':
      return renderStepper({ node, depth, renderChild: (c, d) => renderNode(c, d, ctx) });

    case 'QuoteCard':
      return renderQuoteCard({ node, depth, renderChild: (c, d) => renderNode(c, d, ctx) });

    case 'ImageGallery':
      return renderImageGallery({ node, depth, renderChild: (c, d) => renderNode(c, d, ctx) });

    case 'KeyValueList':
      return renderKeyValueList({ node, depth, renderChild: (c, d) => renderNode(c, d, ctx) });

    default:
      return <UnknownNode key={node.nodeId} node={node} />;
  }
}

export function GenUiTreeView({
  tree,
  contentRef,
  sessionId,
  messageId,
  jsEnabled = false,
}: {
  tree: GenUiTreeV1 | null | undefined;
  /** When set (e.g. GenUiInline screenshot), points at the scrollable tree body only. */
  contentRef?: Ref<HTMLDivElement>;
  /** Enables ``Image`` nodes to resolve ``/files/{id}/preview`` with auth. */
  sessionId?: string;
  /** Assistant message id for GenUi actions (buttons / patches). */
  messageId?: string;
  /** When true, ``HtmlFrame`` nodes may run scripts in sandboxed iframes. */
  jsEnabled?: boolean;
}) {
  const { t } = useTranslation();
  const root = tree?.root;
  const renderCtx = useMemo(
    () => ({ sessionId, messageId, jsEnabled }),
    [sessionId, messageId, jsEnabled],
  );
  const el = useMemo(() => (root ? renderNode(root, 0, renderCtx) : null), [root, renderCtx]);
  /** Outer scroll (GenUiInline, CanvasPanel) supplies scrolling; slot frames use overflow-hidden so body scrolls here. */
  const bodyClass = 'px-4 py-3 min-h-0 text-foreground bg-background';
  if (!root || !el) {
    return (
      <div className="text-sm text-muted-foreground p-4 bg-background">
        No generative UI tree for this message yet.
      </div>
    );
  }
  const rawSlot = root.props && (root.props as Record<string, unknown>).uiSlot;
  const slotKey = typeof rawSlot === 'string' ? rawSlot : null;
  const frame = slotKey ? UI_SLOT_FRAME[slotKey] : null;
  const attribution = t('chat.genUiAttribution');
  const attributionRow = (
    <div
      className="mt-2 flex items-center justify-center gap-1 text-[11px] text-muted-foreground"
      role="note"
      aria-label={attribution}
    >
      <Sparkles className="h-3 w-3 shrink-0 text-primary-500" aria-hidden />
      <span>{attribution}</span>
    </div>
  );
  const inner =
    frame != null ? (
      <div className={frame.className}>
        <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider bg-surface-sunken/80 text-muted-foreground border-b border-border">
          {frame.label}
        </div>
        <div ref={contentRef} className={cn(bodyClass, 'overflow-auto')}>
          {el}
          {attributionRow}
        </div>
      </div>
    ) : (
      <div ref={contentRef} className={bodyClass}>
        {el}
        {attributionRow}
      </div>
    );
  return (
    <GenUiRenderProvider sessionId={sessionId} messageId={messageId} jsEnabled={jsEnabled}>
      {inner}
    </GenUiRenderProvider>
  );
}

export function getHostedCanvasIdFromTree(tree: GenUiTreeV1 | null | undefined): string | null {
  if (!tree?.root) return null;
  const walk = (n: GenUiNode): string | null => {
    if (n.kind === 'HostedCanvasFrame' && n.props && typeof n.props.canvasId === 'string') {
      return n.props.canvasId;
    }
    for (const c of n.children || []) {
      const f = walk(c);
      if (f) return f;
    }
    return null;
  };
  return walk(tree.root);
}

export { renderNode };
