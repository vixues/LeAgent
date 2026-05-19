import {
  forwardRef,
  type HTMLAttributes,
  type ReactNode,
  useMemo,
  useCallback,
} from 'react';
import { cn } from '@/lib/utils';
import {
  ChevronUp,
  ChevronDown,
  ChevronsUpDown,
} from 'lucide-react';
import { Skeleton } from '../ui/Skeleton';
import { EmptyState } from './EmptyState';
import { useTranslation } from 'react-i18next';

export interface Column<T> {
  id: string;
  header: ReactNode | ((props: { column: Column<T> }) => ReactNode);
  cell: (props: { row: T; rowIndex: number }) => ReactNode;
  accessorKey?: keyof T;
  sortable?: boolean;
  width?: string | number;
  minWidth?: string | number;
  maxWidth?: string | number;
  align?: 'left' | 'center' | 'right';
  sticky?: 'left' | 'right';
  hidden?: boolean;
}

export type SortDirection = 'asc' | 'desc' | null;

export interface SortState {
  columnId: string;
  direction: SortDirection;
}

interface DataTableProps<T> extends Omit<HTMLAttributes<HTMLDivElement>, 'children'> {
  data: T[];
  columns: Column<T>[];
  loading?: boolean;
  emptyMessage?: string;
  emptyAction?: { label: string; onClick: () => void };
  sortState?: SortState;
  onSort?: (state: SortState) => void;
  onRowClick?: (row: T, index: number) => void;
  rowKey?: (row: T, index: number) => string | number;
  striped?: boolean;
  hoverable?: boolean;
  bordered?: boolean;
  compact?: boolean;
  stickyHeader?: boolean;
  maxHeight?: string | number;
  selectedRows?: Set<string | number>;
  onRowSelect?: (rowKey: string | number, selected: boolean) => void;
  onSelectAll?: (selected: boolean) => void;
  selectable?: boolean;
}

function DataTableInner<T>(
  {
    className,
    data,
    columns,
    loading = false,
    emptyMessage,
    emptyAction,
    sortState,
    onSort,
    onRowClick,
    rowKey = (_, index) => index,
    striped = false,
    hoverable = true,
    bordered = false,
    compact = false,
    stickyHeader = false,
    maxHeight,
    selectedRows,
    onRowSelect,
    onSelectAll,
    selectable = false,
    ...props
  }: DataTableProps<T>,
  ref: React.ForwardedRef<HTMLDivElement>
) {
  const { t } = useTranslation();
  const visibleColumns = useMemo(
    () => columns.filter((col) => !col.hidden),
    [columns]
  );

  const handleSort = useCallback(
    (columnId: string) => {
      if (!onSort) return;

      let direction: SortDirection = 'asc';
      if (sortState?.columnId === columnId) {
        if (sortState.direction === 'asc') {
          direction = 'desc';
        } else if (sortState.direction === 'desc') {
          direction = null;
        }
      }
      onSort({ columnId, direction });
    },
    [sortState, onSort]
  );

  const getSortIcon = (columnId: string) => {
    if (sortState?.columnId !== columnId || !sortState.direction) {
      return <ChevronsUpDown className="w-4 h-4 text-gray-400" />;
    }
    if (sortState.direction === 'asc') {
      return <ChevronUp className="w-4 h-4" />;
    }
    return <ChevronDown className="w-4 h-4" />;
  };

  const allSelected =
    selectable && data.length > 0 && selectedRows?.size === data.length;
  const someSelected =
    selectable && selectedRows && selectedRows.size > 0 && selectedRows.size < data.length;

  const cellPadding = compact ? 'px-3 py-2' : 'px-4 py-3';

  return (
    <div
      ref={ref}
      className={cn(
        'w-full overflow-auto rounded-lg',
        'border border-gray-200 dark:border-gray-700',
        className
      )}
      style={maxHeight ? { maxHeight } : undefined}
      {...props}
    >
      <table className="w-full border-collapse">
        <thead
          className={cn(
            'bg-gray-50 dark:bg-surface/50',
            stickyHeader && 'sticky top-0 z-10'
          )}
        >
          <tr>
            {selectable && (
              <th
                className={cn(
                  cellPadding,
                  'w-12 text-center',
                  'border-b border-gray-200 dark:border-gray-700'
                )}
              >
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = !!someSelected;
                  }}
                  onChange={(e) => onSelectAll?.(e.target.checked)}
                  className="rounded border-gray-300 dark:border-gray-600"
                />
              </th>
            )}
            {visibleColumns.map((column) => {
              const header =
                typeof column.header === 'function'
                  ? column.header({ column })
                  : column.header;

              return (
                <th
                  key={column.id}
                  className={cn(
                    cellPadding,
                    'text-left text-xs font-semibold uppercase tracking-wider',
                    'text-gray-600 dark:text-gray-400',
                    'border-b border-gray-200 dark:border-gray-700',
                    column.sortable && 'cursor-pointer select-none hover:bg-gray-100 dark:hover:bg-gray-800',
                    column.align === 'center' && 'text-center',
                    column.align === 'right' && 'text-right'
                  )}
                  style={{
                    width: column.width,
                    minWidth: column.minWidth,
                    maxWidth: column.maxWidth,
                  }}
                  onClick={() => column.sortable && handleSort(column.id)}
                >
                  <div
                    className={cn(
                      'flex items-center gap-1',
                      column.align === 'center' && 'justify-center',
                      column.align === 'right' && 'justify-end'
                    )}
                  >
                    {header}
                    {column.sortable && getSortIcon(column.id)}
                  </div>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="bg-surface divide-y divide-gray-200 dark:divide-gray-700">
          {loading ? (
            Array.from({ length: 5 }).map((_, index) => (
              <tr key={index}>
                {selectable && (
                  <td className={cellPadding}>
                    <Skeleton className="h-4 w-4 rounded" />
                  </td>
                )}
                {visibleColumns.map((column) => (
                  <td key={column.id} className={cellPadding}>
                    <Skeleton className="h-4 w-full" />
                  </td>
                ))}
              </tr>
            ))
          ) : data.length === 0 ? (
            <tr>
              <td
                colSpan={visibleColumns.length + (selectable ? 1 : 0)}
                className="py-8"
              >
                <EmptyState
                  type="data"
                  title={emptyMessage || t('common.noData')}
                  action={emptyAction}
                  size="sm"
                />
              </td>
            </tr>
          ) : (
            data.map((row, rowIndex) => {
              const key = rowKey(row, rowIndex);
              const isSelected = selectedRows?.has(key);

              return (
                <tr
                  key={key}
                  className={cn(
                    'transition-colors',
                    striped && rowIndex % 2 === 1 && 'bg-gray-50/50 dark:bg-surface/30',
                    hoverable && 'hover:bg-gray-50 dark:hover:bg-gray-800/50',
                    onRowClick && 'cursor-pointer',
                    isSelected && 'bg-primary-50 dark:bg-primary-900/20'
                  )}
                  onClick={() => onRowClick?.(row, rowIndex)}
                >
                  {selectable && (
                    <td
                      className={cn(cellPadding, 'text-center')}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={(e) => onRowSelect?.(key, e.target.checked)}
                        className="rounded border-gray-300 dark:border-gray-600"
                      />
                    </td>
                  )}
                  {visibleColumns.map((column) => (
                    <td
                      key={column.id}
                      className={cn(
                        cellPadding,
                        'text-sm text-gray-700 dark:text-gray-300',
                        column.align === 'center' && 'text-center',
                        column.align === 'right' && 'text-right',
                        bordered && 'border border-gray-200 dark:border-gray-700'
                      )}
                      style={{
                        width: column.width,
                        minWidth: column.minWidth,
                        maxWidth: column.maxWidth,
                      }}
                    >
                      {column.cell({ row, rowIndex })}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

const DataTable = forwardRef(DataTableInner) as <T>(
  props: DataTableProps<T> & { ref?: React.ForwardedRef<HTMLDivElement> }
) => React.ReactElement;

export { DataTable };
