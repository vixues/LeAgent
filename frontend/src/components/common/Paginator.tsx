import { forwardRef, type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';
import { Button, PRIMARY_SOFT_CTA_CLASSNAME } from '@/components/ui/Button';
import { Select } from '../ui/Select';
import { useTranslation } from 'react-i18next';

interface PaginatorProps extends HTMLAttributes<HTMLDivElement> {
  currentPage: number;
  totalPages: number;
  totalItems?: number;
  pageSize?: number;
  pageSizeOptions?: number[];
  onPageChange: (page: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
  showPageSizeSelector?: boolean;
  showPageInfo?: boolean;
  showFirstLast?: boolean;
  siblingCount?: number;
  compact?: boolean;
}

const Paginator = forwardRef<HTMLDivElement, PaginatorProps>(
  (
    {
      className,
      currentPage,
      totalPages,
      totalItems,
      pageSize = 10,
      pageSizeOptions = [10, 20, 50, 100],
      onPageChange,
      onPageSizeChange,
      showPageSizeSelector = false,
      showPageInfo = true,
      showFirstLast = true,
      siblingCount = 1,
      compact = false,
      ...props
    },
    ref
  ) => {
    const { t } = useTranslation();

    const getPageNumbers = () => {
      const pages: (number | 'ellipsis')[] = [];
      const leftSiblingIndex = Math.max(currentPage - siblingCount, 1);
      const rightSiblingIndex = Math.min(currentPage + siblingCount, totalPages);

      const showLeftEllipsis = leftSiblingIndex > 2;
      const showRightEllipsis = rightSiblingIndex < totalPages - 1;

      if (!showLeftEllipsis && showRightEllipsis) {
        const leftRange = 1 + 2 * siblingCount + 1;
        for (let i = 1; i <= Math.min(leftRange, totalPages); i++) {
          pages.push(i);
        }
        if (totalPages > leftRange + 1) {
          pages.push('ellipsis');
          pages.push(totalPages);
        } else if (totalPages === leftRange + 1) {
          pages.push(totalPages);
        }
      } else if (showLeftEllipsis && !showRightEllipsis) {
        const rightRange = totalPages - (2 * siblingCount + 1);
        pages.push(1);
        if (rightRange > 2) {
          pages.push('ellipsis');
        }
        for (let i = Math.max(rightRange, 2); i <= totalPages; i++) {
          pages.push(i);
        }
      } else if (showLeftEllipsis && showRightEllipsis) {
        pages.push(1);
        pages.push('ellipsis');
        for (let i = leftSiblingIndex; i <= rightSiblingIndex; i++) {
          pages.push(i);
        }
        pages.push('ellipsis');
        pages.push(totalPages);
      } else {
        for (let i = 1; i <= totalPages; i++) {
          pages.push(i);
        }
      }

      return pages;
    };

    const pages = getPageNumbers();
    const canGoPrevious = currentPage > 1;
    const canGoNext = currentPage < totalPages;

    const startItem = totalItems ? (currentPage - 1) * pageSize + 1 : 0;
    const endItem = totalItems ? Math.min(currentPage * pageSize, totalItems) : 0;

    if (compact) {
      return (
        <div
          ref={ref}
          className={cn('flex items-center justify-between gap-4', className)}
          {...props}
        >
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {currentPage} / {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              disabled={!canGoPrevious}
              onClick={() => onPageChange(currentPage - 1)}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              disabled={!canGoNext}
              onClick={() => onPageChange(currentPage + 1)}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      );
    }

    return (
      <div
        ref={ref}
        className={cn(
          'flex flex-col sm:flex-row items-center justify-between gap-4',
          className
        )}
        {...props}
      >
        <div className="flex items-center gap-4">
          {showPageSizeSelector && onPageSizeChange && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500 dark:text-gray-400">
                {t('paginator.perPage')}
              </span>
              <Select
                value={pageSize.toString()}
                onChange={(e) => onPageSizeChange(Number(e.target.value))}
                className="w-20"
              >
                {pageSizeOptions.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </Select>
            </div>
          )}
          {showPageInfo && totalItems !== undefined && (
            <span className="text-sm text-gray-500 dark:text-gray-400">
              {t('paginator.showing', {
                start: startItem,
                end: endItem,
                total: totalItems,
              })}
            </span>
          )}
        </div>

        <nav className="flex items-center gap-1">
          {showFirstLast && (
            <Button
              variant="ghost"
              size="icon"
              disabled={!canGoPrevious}
              onClick={() => onPageChange(1)}
              title={t('paginator.firstPage')}
            >
              <ChevronsLeft className="w-4 h-4" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            disabled={!canGoPrevious}
            onClick={() => onPageChange(currentPage - 1)}
            title={t('paginator.previousPage')}
          >
            <ChevronLeft className="w-4 h-4" />
          </Button>

          <div className="flex items-center gap-1 mx-1">
            {pages.map((page, index) => {
              if (page === 'ellipsis') {
                return (
                  <span
                    key={`ellipsis-${index}`}
                    className="px-2 text-gray-400 dark:text-gray-500"
                  >
                    ...
                  </span>
                );
              }

              const isActive = page === currentPage;
              return (
                <button
                  key={page}
                  type="button"
                  onClick={() => onPageChange(page)}
                  className={cn(
                    'min-w-[2rem] h-8 px-2 text-sm rounded-md transition-colors',
                    isActive
                      ? PRIMARY_SOFT_CTA_CLASSNAME
                      : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                  )}
                >
                  {page}
                </button>
              );
            })}
          </div>

          <Button
            variant="ghost"
            size="icon"
            disabled={!canGoNext}
            onClick={() => onPageChange(currentPage + 1)}
            title={t('paginator.nextPage')}
          >
            <ChevronRight className="w-4 h-4" />
          </Button>
          {showFirstLast && (
            <Button
              variant="ghost"
              size="icon"
              disabled={!canGoNext}
              onClick={() => onPageChange(totalPages)}
              title={t('paginator.lastPage')}
            >
              <ChevronsRight className="w-4 h-4" />
            </Button>
          )}
        </nav>
      </div>
    );
  }
);

Paginator.displayName = 'Paginator';

export { Paginator };
