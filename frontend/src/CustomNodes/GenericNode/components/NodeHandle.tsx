import { Handle, Position } from '@xyflow/react';
import { cn } from '../../../lib/utils';
import { CSSProperties } from 'react';

interface NodeHandleProps {
  type: 'source' | 'target';
  position: Position;
  id?: string;
  isConnected?: boolean;
  isValidConnection?: boolean;
  label?: string;
  className?: string;
  style?: CSSProperties;
}

export function NodeHandle({
  type,
  position,
  id,
  isConnected = false,
  isValidConnection = true,
  label,
  className,
  style,
}: NodeHandleProps) {
  const isHorizontal = position === Position.Left || position === Position.Right;
  const isSource = type === 'source';

  const baseStyle: CSSProperties = {
    ...style,
    transform: position === Position.Left || position === Position.Right
      ? 'translateY(-50%)'
      : 'translateX(-50%)',
  };

  return (
    <div
      className={cn(
        'absolute flex items-center gap-1.5 z-10',
        position === Position.Top && 'top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 flex-col-reverse',
        position === Position.Bottom && 'bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2 flex-col',
        position === Position.Left && 'left-0 -translate-x-1/2 flex-row-reverse',
        position === Position.Right && 'right-0 translate-x-1/2 flex-row',
        className
      )}
      style={baseStyle}
    >
      {label && (
        <span
          className={cn(
            'text-[9px] font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap',
            'bg-surface/80 px-1 py-0.5 rounded',
            isHorizontal && 'hidden sm:block'
          )}
        >
          {label}
        </span>
      )}
      <Handle
        type={type}
        position={position}
        id={id}
        className={cn(
          '!w-3.5 !h-3.5 !border-2 !rounded-full transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-200',
          '!bg-white dark:!bg-gray-800',
          '!shadow-sm',
          isSource
            ? '!border-emerald-500 hover:!border-emerald-400 hover:!bg-emerald-50 dark:hover:!bg-emerald-900/30 hover:!scale-125'
            : '!border-blue-500 hover:!border-blue-400 hover:!bg-blue-50 dark:hover:!bg-blue-900/30 hover:!scale-125',
          isConnected && isSource && '!bg-emerald-500 !border-emerald-600',
          isConnected && !isSource && '!bg-blue-500 !border-blue-600',
          !isValidConnection && '!border-red-500 !bg-red-50 dark:!bg-red-900/30'
        )}
      />
    </div>
  );
}

interface NodeHandleGroupProps {
  handles: Array<{
    id: string;
    label?: string;
    type: 'source' | 'target';
  }>;
  position: Position;
  className?: string;
}

export function NodeHandleGroup({ handles, position, className }: NodeHandleGroupProps) {
  const isVertical = position === Position.Top || position === Position.Bottom;
  const count = handles.length;

  return (
    <div
      className={cn(
        'absolute flex',
        isVertical ? 'flex-row' : 'flex-col',
        position === Position.Top && 'top-0 left-0 right-0 justify-around px-4',
        position === Position.Bottom && 'bottom-0 left-0 right-0 justify-around px-4',
        position === Position.Left && 'left-0 top-0 bottom-0 justify-around py-4',
        position === Position.Right && 'right-0 top-0 bottom-0 justify-around py-4',
        className
      )}
    >
      {handles.map((handle, index) => {
        const offset = count > 1 ? (index / (count - 1)) * 100 : 50;
        
        return (
          <div
            key={handle.id}
            className={cn(
              'relative',
              isVertical && `left-[${offset}%]`,
              !isVertical && `top-[${offset}%]`
            )}
          >
            <NodeHandle
              type={handle.type}
              position={position}
              id={handle.id}
              label={handle.label}
            />
          </div>
        );
      })}
    </div>
  );
}

export default NodeHandle;
