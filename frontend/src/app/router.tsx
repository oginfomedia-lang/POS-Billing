// Route definitions for POS and admin pages.
// Hash routing because the production app is loaded from a file:// URL.
import { createHashRouter } from 'react-router-dom';
import { PosLayout } from '../components/layout/PosLayout';
import { LoginPage } from '../pages/auth/LoginPage';

export const router = createHashRouter([
  {
    element: <PosLayout />,
    children: [{ path: '/', element: <LoginPage /> }],
  },
]);
