// Route definitions for POS and admin pages.
// Hash routing because the production app is loaded from a file:// URL.
import { createHashRouter, Navigate } from 'react-router-dom';
import { PosLayout } from '../components/layout/PosLayout';
import { AuditLogsPage } from '../pages/admin/AuditLogsPage';
import { CategoriesPage } from '../pages/admin/CategoriesPage';
import { CountersPage } from '../pages/admin/CountersPage';
import { CustomersPage } from '../pages/admin/CustomersPage';
import { DashboardPage } from '../pages/admin/DashboardPage';
import { DiscountsPage } from '../pages/admin/DiscountsPage';
import { InventoryPage } from '../pages/admin/InventoryPage';
import { LabelPrintPage } from '../pages/admin/LabelPrintPage';
import { ProductsPage } from '../pages/admin/ProductsPage';
import { ReportsPage } from '../pages/admin/ReportsPage';
import { SettingsPage } from '../pages/admin/SettingsPage';
import { UsersPage } from '../pages/admin/UsersPage';
import { LoginPage } from '../pages/auth/LoginPage';
import { BillingPage } from '../pages/pos/BillingPage';
import { CloseShiftPage } from '../pages/pos/CloseShiftPage';
import { HeldBillsPage } from '../pages/pos/HeldBillsPage';
import { OpenShiftPage } from '../pages/pos/OpenShiftPage';
import { PosPage } from '../pages/pos/PosPage';
import { ReprintPage } from '../pages/pos/ReprintPage';
import { ReturnReceiptPage } from '../pages/pos/ReturnReceiptPage';
import { ReturnsPage } from '../pages/pos/ReturnsPage';
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
          { path: '/pos/billing', element: <BillingPage /> },
          { path: '/pos/shift/open', element: <OpenShiftPage /> },
          { path: '/pos/shift/close', element: <CloseShiftPage /> },
          { path: '/pos/held', element: <HeldBillsPage /> },
          { path: '/pos/reprint/:saleId', element: <ReprintPage /> },
          { path: '/pos/returns', element: <ReturnsPage /> },
          { path: '/pos/return-receipt/:returnId', element: <ReturnReceiptPage /> },
        ],
      },

      // Admin / manager only
      {
        element: <ProtectedRoute roles={['admin', 'manager']} />,
        children: [
          { path: '/admin', element: <DashboardPage /> },
          { path: '/admin/dashboard', element: <DashboardPage /> },
          { path: '/admin/users', element: <UsersPage /> },
          { path: '/admin/audit-logs', element: <AuditLogsPage /> },
          { path: '/admin/products', element: <ProductsPage /> },
          { path: '/admin/categories', element: <CategoriesPage /> },
          { path: '/admin/stores', element: <CountersPage /> },
          { path: '/admin/inventory', element: <InventoryPage /> },
          { path: '/admin/labels', element: <LabelPrintPage /> },
          { path: '/admin/discounts', element: <DiscountsPage /> },
          { path: '/admin/reports', element: <ReportsPage /> },
          { path: '/admin/customers', element: <CustomersPage /> },
          { path: '/admin/settings', element: <SettingsPage /> },
        ],
      },

      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);
