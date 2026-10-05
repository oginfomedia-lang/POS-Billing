// Current user, login and logout helpers.
import { useAuthStore } from '../store/authStore';
import type { UserRole } from '../types/api';

export function useAuth() {
  const { user, token, login, logout } = useAuthStore();
  return {
    user,
    token,
    isAuthenticated: token !== null && user !== null,
    hasRole: (role: UserRole) => user?.role === role,
    isAdmin: user?.role === 'admin',
    isManager: user?.role === 'manager' || user?.role === 'admin',
    login,
    logout,
  };
}
