// Blocks pages when not logged in or without the required role.
import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import type { UserRole } from '../types/api';

interface Props {
  roles?: UserRole[];
}

export function ProtectedRoute({ roles }: Props) {
  const { isAuthenticated, user } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  if (roles && user && !roles.includes(user.role)) {
    return (
      <section className="placeholder-page">
        <h2>Access Denied</h2>
        <p>You don't have permission to view this page.</p>
      </section>
    );
  }

  return <Outlet />;
}
