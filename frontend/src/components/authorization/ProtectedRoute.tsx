import { useEffect } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
import { PageLoader } from '@/components/common/PageLoader';
import { useTranslation } from 'react-i18next';

export function ProtectedRoute({ children }: { children?: React.ReactNode }) {
  const { t } = useTranslation();
  const location = useLocation();
  const { isAuthenticated, isHydratingAuth, authStatus, bootstrapSession } = useAuthStore();

  useEffect(() => {
    void bootstrapSession();
  }, [bootstrapSession]);

  if (isHydratingAuth || authStatus === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <PageLoader message={t('common.meta.starting')} />
      </div>
    );
  }

  if (authStatus.enforce_auth && !isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return children ? <>{children}</> : <Outlet />;
}

export function AuthenticatedGuard({ children }: { children?: React.ReactNode }) {
  return <ProtectedRoute>{children}</ProtectedRoute>;
}

export function RoleGuard({ children }: { children?: React.ReactNode }) {
  return children ? <>{children}</> : <Outlet />;
}

export function PermissionGuard({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

export function PermissionRoute({ children }: { children?: React.ReactNode }) {
  return children ? <>{children}</> : <Outlet />;
}
