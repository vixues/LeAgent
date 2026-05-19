import { memo, useCallback, useState } from 'react';
import { NodeProps, Position, useReactFlow } from '@xyflow/react';
import {
  X,
  FileText,
  Globe,
  Database,
  Bot,
  Mail,
  Bell,
  Clock,
  GitBranch,
  Repeat,
  Webhook,
  Code,
  Image,
  Zap,
  Settings,
  MoreHorizontal,
  Copy,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { NodeHandle } from './components/NodeHandle';
import type { FlowNode } from '../../stores/flow';
import { useFlowStore } from '../../stores/flow';

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  doc: FileText,
  web: Globe,
  data: Database,
  llm: Bot,
  email: Mail,
  notification: Bell,
  delay: Clock,
  condition: GitBranch,
  loop: Repeat,
  webhook: Webhook,
  transform: Code,
  image: Image,
  trigger: Zap,
  default: Settings,
};

const CATEGORY_COLORS: Record<string, { bg: string; border: string; icon: string; accent: string }> = {
  doc: {
    bg: 'bg-orange-50 dark:bg-orange-950/30',
    border: 'border-orange-200 dark:border-orange-800',
    icon: 'text-orange-600 dark:text-orange-400',
    accent: 'bg-orange-500',
  },
  web: {
    bg: 'bg-blue-50 dark:bg-blue-950/30',
    border: 'border-blue-200 dark:border-blue-800',
    icon: 'text-blue-600 dark:text-blue-400',
    accent: 'bg-blue-500',
  },
  data: {
    bg: 'bg-green-50 dark:bg-green-950/30',
    border: 'border-green-200 dark:border-green-800',
    icon: 'text-green-600 dark:text-green-400',
    accent: 'bg-green-500',
  },
  llm: {
    bg: 'bg-blue-50 dark:bg-blue-950/30',
    border: 'border-blue-200 dark:border-blue-800',
    icon: 'text-blue-600 dark:text-blue-400',
    accent: 'bg-blue-500',
  },
  email: {
    bg: 'bg-red-50 dark:bg-red-950/30',
    border: 'border-red-200 dark:border-red-800',
    icon: 'text-red-600 dark:text-red-400',
    accent: 'bg-red-500',
  },
  notification: {
    bg: 'bg-yellow-50 dark:bg-yellow-950/30',
    border: 'border-yellow-200 dark:border-yellow-800',
    icon: 'text-yellow-600 dark:text-yellow-400',
    accent: 'bg-yellow-500',
  },
  delay: {
    bg: 'bg-gray-50 dark:bg-gray-950/30',
    border: 'border-gray-200 dark:border-gray-700',
    icon: 'text-gray-600 dark:text-gray-400',
    accent: 'bg-gray-500',
  },
  condition: {
    bg: 'bg-sky-50 dark:bg-sky-950/30',
    border: 'border-sky-200 dark:border-sky-800',
    icon: 'text-sky-600 dark:text-sky-400',
    accent: 'bg-sky-500',
  },
  loop: {
    bg: 'bg-cyan-50 dark:bg-cyan-950/30',
    border: 'border-cyan-200 dark:border-cyan-800',
    icon: 'text-cyan-600 dark:text-cyan-400',
    accent: 'bg-cyan-500',
  },
  webhook: {
    bg: 'bg-pink-50 dark:bg-pink-950/30',
    border: 'border-pink-200 dark:border-pink-800',
    icon: 'text-pink-600 dark:text-pink-400',
    accent: 'bg-pink-500',
  },
  transform: {
    bg: 'bg-teal-50 dark:bg-teal-950/30',
    border: 'border-teal-200 dark:border-teal-800',
    icon: 'text-teal-600 dark:text-teal-400',
    accent: 'bg-teal-500',
  },
  image: {
    bg: 'bg-rose-50 dark:bg-rose-950/30',
    border: 'border-rose-200 dark:border-rose-800',
    icon: 'text-rose-600 dark:text-rose-400',
    accent: 'bg-rose-500',
  },
  trigger: {
    bg: 'bg-amber-50 dark:bg-amber-950/30',
    border: 'border-amber-200 dark:border-amber-800',
    icon: 'text-amber-600 dark:text-amber-400',
    accent: 'bg-amber-500',
  },
  default: {
    bg: 'bg-slate-50 dark:bg-slate-950/30',
    border: 'border-slate-200 dark:border-slate-700',
    icon: 'text-slate-600 dark:text-slate-400',
    accent: 'bg-slate-500',
  },
};

type GenericNodeProps = NodeProps<FlowNode>;

function GenericNodeComponent({ id, data, selected }: GenericNodeProps) {
  const { deleteElements } = useReactFlow();
  const { addNode, nodes } = useFlowStore();
  const [showMenu, setShowMenu] = useState(false);

  const rawCategory = data.category;
  const category = (rawCategory in CATEGORY_COLORS ? rawCategory : 'default') as keyof typeof CATEGORY_COLORS;
  const colors = (CATEGORY_COLORS[category] ?? CATEGORY_COLORS.default)!;
  const IconComponent = (CATEGORY_ICONS[category] ?? CATEGORY_ICONS.default)!;

  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      deleteElements({ nodes: [{ id }] });
    },
    [deleteElements, id]
  );

  const handleDuplicate = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      setShowMenu(false);

      const currentNode = nodes.find((n) => n.id === id);
      if (!currentNode) return;

      const newNode: FlowNode = {
        id: `${category}-${Date.now()}`,
        type: 'generic',
        position: {
          x: currentNode.position.x + 50,
          y: currentNode.position.y + 50,
        },
        data: { ...data },
      };
      addNode(newNode);
    },
    [id, category, data, nodes, addNode]
  );

  const inputs = data.inputs || ['input'];
  const outputs = data.outputs || ['output'];
  const parameters = data.parameters || {};
  const paramEntries = Object.entries(parameters).slice(0, 3);

  const inputSpacing = 100 / (inputs.length + 1);
  const outputSpacing = 100 / (outputs.length + 1);

  return (
    <div
      className={cn(
        'group relative min-w-[200px] max-w-[280px] rounded-xl border-2 shadow-lg transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-200',
        colors.bg,
        colors.border,
        selected && 'ring-2 ring-primary-500 ring-offset-2 dark:ring-offset-gray-900',
        'hover:shadow-xl'
      )}
    >
      <div className={cn('absolute top-0 left-4 right-4 h-1 rounded-b-full', colors.accent)} />

      {inputs.map((input: string, index: number) => (
        <NodeHandle
          key={`input-${input}`}
          type="target"
          position={Position.Left}
          id={input}
          label={inputs.length > 1 ? input : undefined}
          style={{
            top: `${(index + 1) * inputSpacing}%`,
          }}
        />
      ))}

      {outputs.map((output: string, index: number) => (
        <NodeHandle
          key={`output-${output}`}
          type="source"
          position={Position.Right}
          id={output}
          label={outputs.length > 1 ? output : undefined}
          style={{
            top: `${(index + 1) * outputSpacing}%`,
          }}
        />
      ))}

      <div className="p-3 pt-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <div
              className={cn(
                'flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center',
                'bg-surface shadow-sm',
                'border',
                colors.border
              )}
            >
              <IconComponent className={cn('w-4.5 h-4.5', colors.icon)} />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="font-semibold text-sm text-gray-900 dark:text-white truncate leading-tight">
                {data.label}
              </h3>
              {data.description && (
                <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5 leading-tight">
                  {data.description}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
            <div className="relative">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setShowMenu(!showMenu);
                }}
                className={cn(
                  'p-1.5 rounded-md transition-colors',
                  'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300',
                  'hover:bg-white/50 dark:hover:bg-gray-700/50'
                )}
                title="More actions"
              >
                <MoreHorizontal className="w-3.5 h-3.5" />
              </button>

              {showMenu && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowMenu(false);
                    }}
                  />
                  <div className="absolute right-0 top-full mt-1 w-36 bg-surface rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-1 z-20">
                    <button
                      onClick={handleDuplicate}
                      className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                    >
                      <Copy className="w-3.5 h-3.5" />
                      Duplicate
                    </button>
                    <button
                      onClick={handleDelete}
                      className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30"
                    >
                      <X className="w-3.5 h-3.5" />
                      Delete
                    </button>
                  </div>
                </>
              )}
            </div>

            <button
              onClick={handleDelete}
              className={cn(
                'p-1.5 rounded-md transition-colors',
                'text-gray-400 hover:text-red-500',
                'hover:bg-red-50 dark:hover:bg-red-900/30'
              )}
              title="Delete node"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {paramEntries.length > 0 && (
          <div className="mt-3 pt-2 border-t border-gray-200/70 dark:border-gray-700/70 space-y-1.5">
            {paramEntries.map(([key, value]) => {
              const displayKey = key.replace(/([A-Z])/g, ' $1').trim();
              const displayValue = value === '' ? '—' : String(value);
              const isLongValue = displayValue.length > 15;

              return (
                <div key={key} className="flex items-center justify-between text-xs gap-2">
                  <span className="text-gray-500 dark:text-gray-400 capitalize truncate flex-shrink-0">
                    {displayKey}
                  </span>
                  <span
                    className={cn(
                      'font-mono text-gray-700 dark:text-gray-300 truncate text-right',
                      isLongValue ? 'max-w-[80px]' : 'max-w-[120px]'
                    )}
                    title={displayValue}
                  >
                    {displayValue}
                  </span>
                </div>
              );
            })}
            {Object.keys(parameters).length > 3 && (
              <p className="text-[10px] text-gray-400 dark:text-gray-500 pt-0.5">
                +{Object.keys(parameters).length - 3} more parameters
              </p>
            )}
          </div>
        )}

        <div className="mt-2.5 flex items-center justify-between">
          <span
            className={cn(
              'text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wider',
              colors.bg,
              colors.icon,
              'border',
              colors.border
            )}
          >
            {category}
          </span>

          <div className="flex items-center gap-1.5 text-[10px] text-gray-400 dark:text-gray-500">
            {inputs.length > 0 && (
              <span className="flex items-center gap-0.5">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
                {inputs.length}
              </span>
            )}
            {outputs.length > 0 && (
              <span className="flex items-center gap-0.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                {outputs.length}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export const GenericNode = memo(GenericNodeComponent);
export default GenericNode;
