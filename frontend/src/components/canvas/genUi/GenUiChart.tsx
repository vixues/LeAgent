import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { GenUiNode } from '@/types/genUi';
import { cn } from '@/lib/utils';

/** Fallback series hues when CSS vars are unavailable; readable on light + dark surfaces. */
const SERIES_FALLBACK = [
  'hsl(199 89% 48%)',
  'hsl(142 71% 45%)',
  'hsl(262 83% 58%)',
  'hsl(38 92% 50%)',
  'hsl(347 77% 50%)',
];

function useChartCss() {
  const [ver, setVer] = useState(0);
  useEffect(() => {
    const el = document.documentElement;
    const obs = new MutationObserver(() => setVer((v) => v + 1));
    obs.observe(el, { attributes: true, attributeFilter: ['class'] });
    return () => obs.disconnect();
  }, []);

  return useMemo(() => {
    const cs = getComputedStyle(document.documentElement);
    const g = (n: string) => {
      const v = cs.getPropertyValue(n).trim();
      return v ? `rgb(${v})` : undefined;
    };
    return {
      text: g('--color-text') ?? '#171717',
      textMuted: g('--color-text-secondary') ?? '#5b5b61',
      border: g('--color-border') ?? '#e8e6e2',
      surface: g('--color-surface') ?? '#ffffff',
      primary: g('--color-primary') ?? SERIES_FALLBACK[0],
    };
  }, [ver]);
}

export function GenUiChart({ node }: { node: GenUiNode }) {
  const p = (node.props || {}) as Record<string, unknown>;
  const chartKind = ((p.chart as string) || 'line').toLowerCase();
  const title = typeof p.title === 'string' ? p.title : '';
  const height = typeof p.height === 'number' && p.height > 0 ? p.height : 280;
  const showLegend = p.showLegend !== false;
  const showGrid = p.showGrid !== false;
  const stacked = Boolean(p.stacked);

  const categories = Array.isArray(p.categories) ? p.categories.map((c) => String(c)) : [];
  const seriesRaw = Array.isArray(p.series) ? p.series : [];
  const series = seriesRaw
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const o = item as Record<string, unknown>;
      const name = String(o.name ?? '');
      const rawVals = o.values;
      const values = Array.isArray(rawVals)
        ? rawVals.map((v) => {
            const n = typeof v === 'number' ? v : Number(v);
            return Number.isFinite(n) ? n : 0;
          })
        : [];
      return { name, values };
    })
    .filter((x): x is { name: string; values: number[] } => x !== null);

  const css = useChartCss();
  const palette = useMemo(() => {
    const rest = SERIES_FALLBACK.filter((c) => c !== SERIES_FALLBACK[0]);
    return [css.primary, ...rest.slice(0, 4)];
  }, [css.primary]);

  const cartesianData = useMemo(() => {
    const lens = series.map((s) => s.values.length);
    const n = Math.max(categories.length, lens.length ? Math.max(...lens) : 0);
    if (n === 0) return [];
    const rows: Record<string, string | number>[] = [];
    for (let i = 0; i < n; i++) {
      const row: Record<string, string | number> = {
        name: categories[i] ?? String(i + 1),
      };
      series.forEach((ser, j) => {
        row[`s${j}`] = ser.values[i] ?? 0;
      });
      rows.push(row);
    }
    return rows;
  }, [categories, series]);

  const pieData = useMemo(() => {
    const ser = series[0];
    if (!ser) return [];
    const n = Math.max(ser.values.length, categories.length);
    return Array.from({ length: n }, (_, i) => ({
      name: categories[i] ?? `Item ${i + 1}`,
      value: ser.values[i] ?? 0,
    }));
  }, [categories, series]);

  const tooltipStyle = useMemo(
    () => ({
      backgroundColor: css.surface,
      border: `1px solid ${css.border}`,
      borderRadius: 8,
      fontSize: 12,
      color: css.text,
    }),
    [css.border, css.surface, css.text],
  );

  const axisProps = {
    tick: { fill: css.textMuted, fontSize: 11 },
    axisLine: { stroke: css.border },
    tickLine: { stroke: css.border },
  };

  if (chartKind === 'pie') {
    if (!pieData.length) {
      return (
        <div className="rounded-xl border border-dashed border-border bg-surface-sunken/40 px-4 py-8 text-center text-sm text-muted-foreground">
          No chart data
        </div>
      );
    }
    const outerR = Math.min(height * 0.36, 140);
    return (
      <figure className={cn('w-full min-w-0 space-y-2')}>
        {title ? <figcaption className="text-sm font-semibold text-foreground">{title}</figcaption> : null}
        <div style={{ height }} className="w-full min-h-[200px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={pieData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={outerR}
                paddingAngle={2}
              >
                {pieData.map((_, i) => (
                  <Cell key={i} fill={palette[i % palette.length]} stroke={css.border} strokeWidth={1} />
                ))}
              </Pie>
              {showLegend ? <Legend wrapperStyle={{ fontSize: 12, color: css.textMuted }} /> : null}
              <Tooltip contentStyle={tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </figure>
    );
  }

  if (!series.length || !cartesianData.length) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-surface-sunken/40 px-4 py-8 text-center text-sm text-muted-foreground">
        No chart data
      </div>
    );
  }

  const grid = showGrid ? (
    <CartesianGrid strokeDasharray="3 3" stroke={css.border} opacity={0.55} />
  ) : null;

  const axes = (
    <>
      {grid}
      <XAxis dataKey="name" {...axisProps} />
      <YAxis {...axisProps} width={40} />
      <Tooltip contentStyle={tooltipStyle} />
      {showLegend ? <Legend wrapperStyle={{ fontSize: 12, color: css.textMuted }} /> : null}
    </>
  );

  let chartBody: ReactNode;
  if (chartKind === 'bar') {
    chartBody = (
      <BarChart data={cartesianData} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
        {axes}
        {series.map((_, j) => (
          <Bar
            key={j}
            dataKey={`s${j}`}
            name={series[j]?.name ? series[j].name : `Series ${j + 1}`}
            fill={palette[j % palette.length]}
            stackId={stacked ? 'stack' : undefined}
            radius={[4, 4, 0, 0]}
          />
        ))}
      </BarChart>
    );
  } else if (chartKind === 'area') {
    chartBody = (
      <AreaChart data={cartesianData} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
        {axes}
        {series.map((_, j) => (
          <Area
            key={j}
            type="monotone"
            dataKey={`s${j}`}
            name={series[j]?.name ? series[j].name : `Series ${j + 1}`}
            stroke={palette[j % palette.length]}
            fill={palette[j % palette.length]}
            fillOpacity={0.22}
            strokeWidth={2}
            stackId={stacked ? 'stack' : undefined}
          />
        ))}
      </AreaChart>
    );
  } else {
    chartBody = (
      <LineChart data={cartesianData} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
        {axes}
        {series.map((_, j) => (
          <Line
            key={j}
            type="monotone"
            dataKey={`s${j}`}
            name={series[j]?.name ? series[j].name : `Series ${j + 1}`}
            stroke={palette[j % palette.length]}
            strokeWidth={2}
            dot={{ r: 3, fill: palette[j % palette.length] }}
            activeDot={{ r: 5 }}
          />
        ))}
      </LineChart>
    );
  }

  return (
    <figure className={cn('w-full min-w-0 space-y-2')}>
      {title ? <figcaption className="text-sm font-semibold text-foreground">{title}</figcaption> : null}
      <div style={{ height }} className="w-full min-h-[200px]">
        <ResponsiveContainer width="100%" height="100%">
          {chartBody}
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
