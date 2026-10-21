// Blocks pages when not logged in or without the required role.
import { useTranslation } from 'react-i18next';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import type { UserRole } from '../types/api';

interface Props {
  roles?: UserRole[];
}

export function ProtectedRoute({ roles }: Props) {
  const { t } = useTranslation();
  const { isAuthenticated, user } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }
  if (user?.must_change_pin) {
    return <Navigate to="/change-pin" replace />;
  }

  if (roles && user && !roles.includes(user.role)) {
    return (
      <section className="placeholder-page">
        <h2>{t('app.accessDenied')}</h2>
        <p>{t('app.noPermission')}</p>
      </section>
    );
  }

  return <Outlet />;
}
