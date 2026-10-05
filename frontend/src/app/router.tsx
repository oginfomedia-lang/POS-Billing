// Route definitions for POS and admin pages.
// Hash routing because the production app is loaded from a file:// URL.
import { createHashRouter, Navigate } from 'react-router-dom';
import { PosLayout } from '../components/layout/PosLayout';
import { AuditLogsPage } from '../pages/admin/AuditLogsPage';
import { UsersPage } from '../pages/admin/UsersPage';
import { LoginPage } from '../pages/auth/LoginPage';
import { PosPage } from '../pages/pos/PosPage';
import { ProtectedRoute } from './ProtectedRoute';

export const router = createHashRouter([
  {
    element: <PosLayout />,
    children: [
      { path: '/', element: <LoginPage /> },

      // Any authenticated user
      {
        element: <ProtectedRoute />,
        children: [
          { path: '/pos', element: <PosPage /> },
        ],
      },

      // Admin / manager only
      {
        element: <ProtectedRoute roles={['admin', 'manager']} />,
        children: [
          { path: '/admin/users', element: <UsersPage /> },
          { path: '/admin/audit-logs', element: <AuditLogsPage /> },
        ],
      },

      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);
