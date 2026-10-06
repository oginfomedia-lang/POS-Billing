// Top navigation shared by all admin pages (links depend on role).
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

const LINKS: { to: string; label: string; adminOnly?: boolean }[] = [
  { to: '/admin', label: 'Dashboard' },
  { to: '/admin/users', label: 'Users' },
  { to: '/admin/stores', label: 'Stores & Counters' },
  { to: '/admin/products', label: 'Products' },
  { to: '/admin/labels', label: 'Print Labels' },
  { to: '/admin/categories', label: 'Categories' },
  { to: '/admin/inventory', label: 'Inventory' },
  { to: '/admin/discounts', label: 'Discounts' },
  { to: '/admin/reports', label: 'Reports' },
  { to: '/admin/settings', label: 'Settings' },
  { to: '/admin/audit-logs', label: 'Audit Logs', adminOnly: true },
];

export function AdminNav() {
  const { isAdmin, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <nav className="admin-nav no-print">
      {LINKS.filter((l) => isAdmin || !l.adminOnly).map((l) => (
        <NavLink key={l.to} to={l.to} className={({ isActive }) => `admin-nav-link${isActive ? ' active' : ''}`}>
          {l.label}
        </NavLink>
      ))}
      <span className="admin-nav-spacer" />
      <button className="btn-secondary" onClick={() => navigate('/pos')}>POS</button>
      <button className="btn-secondary" onClick={logout}>Logout</button>
    </nav>
  );
}
