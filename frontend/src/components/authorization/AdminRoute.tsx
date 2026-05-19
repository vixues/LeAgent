import { Outlet } from 'react-router-dom';

export function AdminRoute({ children }: { children?: React.ReactNode }) {
  return children ? <>{children}</> : <Outlet />;
}

export function AdminOnly({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

export function ModeratorRoute({ children }: { children?: React.ReactNode }) {
  return children ? <>{children}</> : <Outlet />;
}

export function UnauthorizedView() {
  return null;
}
