import { memo, useCallback, useState } from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  EdgeProps,
  getBezierPath,
  getSmoothStepPath,
  useReactFlow,
} from '@xyflow/react';
import { X } from 'lucide-react';
import { cn } from '../lib/utils';

interface DefaultEdgeData {
  animated?: boolean;
  pathType?: 'bezier' | 'smoothstep';
  label?: string;
}

interface DefaultEdgeProps extends EdgeProps {
  animated?: boolean;
}

function DefaultEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  selected,
  data: rawData,
}: DefaultEdgeProps) {
  const data = rawData as DefaultEdgeData | undefined;
  const { deleteElements } = useReactFlow();
  const [isHovered, setIsHovered] = useState(false);

  const animated = data?.animated ?? false;
  const pathType = data?.pathType ?? 'bezier';

  const pathParams = {
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  };

  const [edgePath, labelX, labelY] =
    pathType === 'smoothstep'
      ? getSmoothStepPath({ ...pathParams, borderRadius: 8 })
      : getBezierPath(pathParams);

  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      deleteElements({ edges: [{ id: id as string }] });
    },
    [deleteElements, id]
  );

  const strokeColor = selected ? '#0284c7' : isHovered ? '#38bdf8' : '#94a3b8';
  const strokeWidth = selected ? 3 : isHovered ? 2.5 : 2;

  return (
    <>
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        style={{ cursor: 'pointer' }}
      />

      <BaseEdge
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          ...(style as React.CSSProperties),
          strokeWidth,
          stroke: strokeColor,
          strokeLinecap: 'round',
          strokeLinejoin: 'round',
        }}
        className={cn(
          'transition-[color,opacity,stroke] duration-200',
          selected && 'drop-shadow-md'
        )}
      />

      {animated && (
        <path
          d={edgePath}
          fill="none"
          stroke={strokeColor}
          strokeWidth={strokeWidth}
          strokeDasharray="5 5"
          className="animate-dash"
          style={{
            strokeLinecap: 'round',
          }}
        />
      )}

      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'all',
          }}
          className="nodrag nopan"
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
        >
          {data?.label && (
            <span
              className={cn(
                'absolute -top-6 left-1/2 -translate-x-1/2 whitespace-nowrap',
                'px-2 py-0.5 text-[10px] font-medium rounded-full',
                'bg-surface border border-gray-200 dark:border-gray-700',
                'text-gray-600 dark:text-gray-400 shadow-sm',
                'opacity-0 transition-opacity duration-200',
                (isHovered || selected) && 'opacity-100'
              )}
            >
              {data.label}
            </span>
          )}

          <button
            onClick={handleDelete}
            className={cn(
              'flex items-center justify-center w-5 h-5 rounded-full',
              'bg-surface border border-gray-200 dark:border-gray-700',
              'text-gray-400 hover:text-red-500 hover:border-red-300 dark:hover:border-red-700',
              'shadow-sm hover:shadow transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-200',
              'opacity-0 hover:opacity-100 focus:opacity-100',
              (selected || isHovered) && 'opacity-100',
              'hover:scale-110'
            )}
            title="Delete connection"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      </EdgeLabelRenderer>

      <style>{`
        @keyframes dash {
          to {
            stroke-dashoffset: -20;
          }
        }
        .animate-dash {
          animation: dash 0.5s linear infinite;
        }
      `}</style>
    </>
  );
}

export const DefaultEdge = memo(DefaultEdgeComponent);
export default DefaultEdge;
