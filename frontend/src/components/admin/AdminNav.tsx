// Admin navigation shared by all admin pages (links depend on role).
// Desktop: fixed sidebar. Below 1024px: sticky top bar + slide-in drawer.
import React, { useEffect, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import {
  IconBarChart,
  IconBoxes,
  IconDashboard,
  IconFileText,
  IconFolder,
  IconLogOut,
  IconMenu,
  IconPackage,
  IconPercent,
  IconSettings,
  IconShoppingCart,
  IconStore,
  IconTag,
  IconUsers,
  IconX,
} from '../common/Icons';

interface LinkItem {
  to: string;
  label: string;
  icon: React.FC<{ size?: number; color?: string }>;
  adminOnly?: boolean;
}

const SECTIONS: { title: string; links: LinkItem[] }[] = [
  {
    title: 'Overview',
    links: [
      { to: '/admin', label: 'Dashboard', icon: IconDashboard },
      { to: '/admin/reports', label: 'Reports', icon: IconBarChart },
    ],
  },
  {
    title: 'Catalog',
    links: [
      { to: '/admin/products', label: 'Products', icon: IconPackage },
      { to: '/admin/categories', label: 'Categories', icon: IconFolder },
      { to: '/admin/inventory', label: 'Stock / Inventory', icon: IconBoxes },
      { to: '/admin/labels', label: 'Print Labels', icon: IconTag },
      { to: '/admin/discounts', label: 'Offers & Discounts', icon: IconPercent },
    ],
  },
  {
    title: 'Administration',
    links: [
      { to: '/admin/stores', label: 'Stores & Counters', icon: IconStore },
      { to: '/admin/users', label: 'Staff & Users', icon: IconUsers },
      { to: '/admin/settings', label: 'Settings', icon: IconSettings },
      { to: '/admin/audit-logs', label: 'Audit Logs', icon: IconFileText, adminOnly: true },
    ],
  },
];

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('');
}

function Brand() {
  return (
    <div className="admin-brand">
      <div className="brand-logo-icon">
        <IconShoppingCart size={20} color="#ffffff" />
      </div>
      <div className="brand-titles">
        <span className="brand-name">Supermarket POS</span>
        <span className="brand-sub">Management Portal</span>
      </div>
    </div>
  );
}

export function AdminNav() {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const displayName = user?.full_name || user?.username || '';

  return (
    <>
      <header className="admin-mobilebar no-print">
        <button
          className="mobile-menu-toggle"
          onClick={() => setOpen(true)}
          aria-label="Open navigation menu"
          aria-expanded={open}
        >
          <IconMenu size={22} />
        </button>
        <Brand />
        <button className="btn-pos-launch btn-pos-launch-compact" onClick={() => navigate('/pos')} title="Open POS Counter">
          <IconShoppingCart size={16} />
          <span>POS</span>
        </button>
      </header>

      <div
        className={`admin-drawer-backdrop no-print${open ? ' open' : ''}`}
        onClick={() => setOpen(false)}
        aria-hidden="true"
      />

      <aside className={`admin-sidebar no-print${open ? ' open' : ''}`} aria-label="Admin navigation">
        <div className="sidebar-head">
          <Brand />
          <button className="sidebar-close" onClick={() => setOpen(false)} aria-label="Close navigation menu">
            <IconX size={20} />
          </button>
        </div>

        <nav className="admin-nav">
          {SECTIONS.map((section) => {
            const links = section.links.filter((l) => isAdmin || !l.adminOnly);
            if (links.length === 0) return null;
            return (
              <div key={section.title} className="nav-section">
                <span className="nav-section-title">{section.title}</span>
                {links.map((l) => {
                  const Icon = l.icon;
                  return (
                    <NavLink
                      key={l.to}
                      to={l.to}
                      end={l.to === '/admin'}
                      className={({ isActive }) => `admin-nav-link${isActive ? ' active' : ''}`}
                      onClick={() => setOpen(false)}
                    >
                      <Icon size={18} />
                      <span>{l.label}</span>
                    </NavLink>
                  );
                })}
              </div>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <button className="btn-pos-launch" onClick={() => navigate('/pos')}>
            <IconShoppingCart size={16} />
            <span>Open POS Counter</span>
          </button>
          {user && (
            <div className="user-card">
              <span className="user-avatar">{initials(displayName)}</span>
              <div className="user-meta">
                <span className="user-name">{displayName}</span>
                <span className={`role-badge role-${user.role}`}>{user.role}</span>
              </div>
              <button className="btn-logout" onClick={logout} title="Sign out" aria-label="Sign out">
                <IconLogOut size={18} />
              </button>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
