import { Component, type ErrorInfo, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';
import { Button } from '../ui/Button';
import { cn } from '@/lib/utils';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  onReset?: () => void;
  showDetails?: boolean;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });
    this.props.onError?.(error, errorInfo);

    if (process.env.NODE_ENV === 'development') {
      console.error('ErrorBoundary caught an error:', error, errorInfo);
    }
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
    this.props.onReset?.();
  };

  handleGoHome = () => {
    this.handleReset();
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <ErrorFallback
          error={this.state.error}
          errorInfo={this.state.errorInfo}
          onReset={this.handleReset}
          onGoHome={this.handleGoHome}
          showDetails={this.props.showDetails}
        />
      );
    }

    return this.props.children;
  }
}

interface ErrorFallbackProps {
  error: Error | null;
  errorInfo?: ErrorInfo | null;
  onReset?: () => void;
  onGoHome?: () => void;
  showDetails?: boolean;
  title?: string;
  description?: string;
}

const ErrorFallback = ({
  error,
  errorInfo,
  onReset,
  onGoHome,
  showDetails = process.env.NODE_ENV === 'development',
  title,
  description,
}: ErrorFallbackProps) => {
  const { t } = useTranslation();
  const resolvedTitle = title ?? t('errors.errorBoundaryTitle');
  const resolvedDescription = description ?? t('errors.errorBoundaryDescription');

  return (
    <div className="min-h-[400px] flex items-center justify-center p-6">
      <div className="max-w-lg w-full text-center">
        <div
          className={cn(
            'mx-auto w-16 h-16 rounded-full flex items-center justify-center mb-6',
            'bg-red-100 dark:bg-red-900/30'
          )}
        >
          <AlertTriangle className="w-8 h-8 text-red-600 dark:text-red-400" />
        </div>

        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
          {resolvedTitle}
        </h2>
        <p className="text-gray-500 dark:text-gray-400 mb-6">{resolvedDescription}</p>

        <div className="flex items-center justify-center gap-3 mb-6">
          {onReset && (
            <Button onClick={onReset} leftIcon={<RefreshCw className="w-4 h-4" />}>
              {t('common.retry')}
            </Button>
          )}
          {onGoHome && (
            <Button
              variant="outline"
              onClick={onGoHome}
              leftIcon={<Home className="w-4 h-4" />}
            >
              {t('common.goHome')}
            </Button>
          )}
        </div>

        {showDetails && error && (
          <div
            className={cn(
              'text-left p-4 rounded-lg overflow-auto max-h-48',
              'bg-gray-100 dark:bg-surface',
              'border border-gray-200 dark:border-gray-700'
            )}
          >
            <p className="text-sm font-medium text-red-600 dark:text-red-400 mb-2">
              {error.name}: {error.message}
            </p>
            {errorInfo && (
              <pre className="text-xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
                {errorInfo.componentStack}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

interface AsyncBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

const AsyncBoundary = ({ children, fallback, onError }: AsyncBoundaryProps) => {
  return (
    <ErrorBoundary fallback={fallback} onError={onError}>
      {children}
    </ErrorBoundary>
  );
};

export { ErrorBoundary, ErrorFallback, AsyncBoundary };
