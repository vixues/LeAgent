import { Outlet } from 'react-router-dom';

export function ProtectedRoute({ children }: { children?: React.ReactNode }) {
  return children ? <>{children}</> : <Outlet />;
}

export function AuthenticatedGuard({ children }: { children?: React.ReactNode }) {
  return children ? <>{children}</> : <Outlet />;
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
