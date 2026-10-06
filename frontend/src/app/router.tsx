// Route definitions for POS and admin pages.
// Hash routing because the production app is loaded from a file:// URL.
import { createHashRouter, Navigate } from 'react-router-dom';
import { PosLayout } from '../components/layout/PosLayout';
import { AuditLogsPage } from '../pages/admin/AuditLogsPage';
import { UsersPage } from '../pages/admin/UsersPage';
import { LoginPage } from '../pages/auth/LoginPage';
import { BillingPage } from '../pages/pos/BillingPage';
import { HeldBillsPage } from '../pages/pos/HeldBillsPage';
import { OpenShiftPage } from '../pages/pos/OpenShiftPage';
import { PosPage } from '../pages/pos/PosPage';
import { ReprintPage } from '../pages/pos/ReprintPage';
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
          { path: '/pos/open-shift', element: <OpenShiftPage /> },
          { path: '/pos/billing', element: <BillingPage /> },
          { path: '/pos/held', element: <HeldBillsPage /> },
          { path: '/pos/reprint/:saleId', element: <ReprintPage /> },
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
