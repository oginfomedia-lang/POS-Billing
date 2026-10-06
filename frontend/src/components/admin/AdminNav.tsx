// Top navigation shared by all admin pages (links depend on role).
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

const LINKS: { to: string; label: string; adminOnly?: boolean }[] = [
  { to: '/admin/users', label: 'Users' },
  { to: '/admin/stores', label: 'Stores & Counters' },
  { to: '/admin/products', label: 'Products' },
  { to: '/admin/categories', label: 'Categories' },
  { to: '/admin/inventory', label: 'Inventory' },
  { to: '/admin/audit-logs', label: 'Audit Logs', adminOnly: true },
];

export function AdminNav() {
  const { isAdmin, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <nav className="admin-nav">
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
