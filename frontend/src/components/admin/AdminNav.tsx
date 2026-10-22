// Admin navigation shared by all admin pages (links depend on role).
// Desktop: fixed sidebar. Below 1024px: sticky top bar + slide-in drawer.
import type { ParseKeys } from 'i18next';
import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { hasPrinterBridge } from '../../services/hardware/printerService';
import {
  IconBarChart,
  IconBoxes,
  IconClipboardList,
  IconDashboard,
  IconDatabase,
  IconFileText,
  IconFolder,
  IconLogOut,
  IconMenu,
  IconPackage,
  IconPercent,
  IconReceipt,
  IconSettings,
  IconShoppingCart,
  IconStore,
  IconTag,
  IconTruck,
  IconUsers,
  IconX,
} from '../common/Icons';
import { useStoreContext, useStoreDisplayName } from '../../store/storeContext';
import { VENDOR_NAME } from '../../utils/brand';
import { StoreSwitcher } from './StoreSwitcher';

interface LinkItem {
  to: string;
  label: ParseKeys;
  icon: React.FC<{ size?: number; color?: string }>;
  adminOnly?: boolean;
}

/** Parts of the Settings page, shown as a tree under Settings: one click goes straight there. */
const SETTINGS_SECTIONS: { id: string; label: ParseKeys; adminOnly?: boolean; printerOnly?: boolean }[] = [
  { id: 'general', label: 'nav.settingsGeneral' },
  { id: 'rewards', label: 'settings.rewards.title' },
  { id: 'ebill', label: 'settings.ebill.title' },
  { id: 'cardupi', label: 'settings.cardUpi.title' },
  { id: 'scale', label: 'settings.scale.title' },
  { id: 'daily-report', label: 'settings.dailyReport.title' },
  { id: 'integrations', label: 'settings.integrations.title', adminOnly: true },
  { id: 'printer', label: 'printer.title', printerOnly: true },
];

// Titles and labels are translation keys, turned into text with t() when rendering.
const SECTIONS: { title: ParseKeys; links: LinkItem[] }[] = [
  {
    title: 'nav.overview',
    links: [
      { to: '/admin', label: 'nav.dashboard', icon: IconDashboard },
      { to: '/admin/reports', label: 'nav.reports', icon: IconBarChart },
      { to: '/admin/bills', label: 'nav.bills', icon: IconReceipt },
      { to: '/admin/customers', label: 'nav.customers', icon: IconUsers },
    ],
  },
  {
    title: 'nav.catalog',
    links: [
      { to: '/admin/products', label: 'nav.products', icon: IconPackage },
      { to: '/admin/categories', label: 'nav.categories', icon: IconFolder },
      { to: '/admin/inventory', label: 'nav.inventory', icon: IconBoxes },
      { to: '/admin/labels', label: 'nav.labels', icon: IconTag },
      { to: '/admin/discounts', label: 'nav.discounts', icon: IconPercent },
      { to: '/admin/suppliers', label: 'nav.suppliers', icon: IconTruck },
    ],
  },
  {
    title: 'nav.purchasing',
    links: [
      { to: '/admin/purchases', label: 'nav.purchases', icon: IconClipboardList },
    ],
  },
  {
    title: 'nav.administration',
    links: [
      { to: '/admin/stores', label: 'nav.stores', icon: IconStore },
      { to: '/admin/users', label: 'nav.users', icon: IconUsers },
      { to: '/admin/settings', label: 'nav.settings', icon: IconSettings },
      { to: '/admin/audit-logs', label: 'nav.auditLogs', icon: IconFileText, adminOnly: true },
      { to: '/admin/backups', label: 'nav.backups', icon: IconDatabase, adminOnly: true },
    ],
  },
];

// Every admin page draws its own AdminNav, so the list would start at the top again on each click: keep where it
// was scrolled to across pages.
let navScrollTop = 0;

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('');
}

function Brand() {
  const { t } = useTranslation();
  const name = useStoreDisplayName();
  return (
    <div className="admin-brand">
      <div className="brand-logo-icon">
        <IconShoppingCart size={20} color="#ffffff" />
      </div>
      <div className="brand-titles">
        <span className="brand-name" title={name}>
          {name}
        </span>
        <span className="brand-sub">{t('app.portal')}</span>
      </div>
    </div>
  );
}

export function AdminNav() {
  const { t } = useTranslation();
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const onSettings = location.pathname === '/admin/settings';
  const currentSection = onSettings ? new URLSearchParams(location.search).get('section') : null;
  // The Settings tree is open on the Settings page; elsewhere the arrow opens it.
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsExpanded = onSettings || settingsOpen;
  const settingsSections = SETTINGS_SECTIONS.filter(
    (s) => (isAdmin || !s.adminOnly) && (!s.printerOnly || hasPrinterBridge()),
  );
  const navRef = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    nav.scrollTop = navScrollTop;
    // Opened at a page whose link is out of sight (e.g. from the dashboard's shortcuts): bring it into view.
    nav.querySelector('.admin-nav-link.active')?.scrollIntoView({ block: 'nearest' });
  }, []);
  const { loaded, refresh } = useStoreContext();
  const storeName = useStoreDisplayName();
  useEffect(() => { if (!loaded) refresh().catch(() => {}); }, [loaded]);
  useEffect(() => { document.title = `${storeName} — POS`; }, [storeName]);


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
          aria-label={t('nav.openMenu')}
          aria-expanded={open}
        >
          <IconMenu size={22} />
        </button>
        <Brand />
        <button className="btn-pos-launch btn-pos-launch-compact" onClick={() => navigate('/pos')} title={t('nav.openPos')}>
          <IconShoppingCart size={16} />
          <span>{t('nav.pos')}</span>
        </button>
      </header>

      <div
        className={`admin-drawer-backdrop no-print${open ? ' open' : ''}`}
        onClick={() => setOpen(false)}
        aria-hidden="true"
      />

      <aside className={`admin-sidebar no-print${open ? ' open' : ''}`} aria-label={t('nav.adminNav')}>
        <div className="sidebar-head">
          <Brand />
          <button className="sidebar-close" onClick={() => setOpen(false)} aria-label={t('nav.closeMenu')}>
            <IconX size={20} />
          </button>
        </div>

        <StoreSwitcher />

        <nav className="admin-nav" ref={navRef} onScroll={(e) => { navScrollTop = e.currentTarget.scrollTop; }}>
          {SECTIONS.map((section) => {
            const links = section.links.filter((l) => isAdmin || !l.adminOnly);
            if (links.length === 0) return null;
            return (
              <div key={section.title} className="nav-section">
                <span className="nav-section-title">{t(section.title)}</span>
                {links.map((l) => {
                  const Icon = l.icon;
                  const isSettings = l.to === '/admin/settings';
                  return (
                    <React.Fragment key={l.to}>
                      <div className={isSettings ? 'nav-link-row' : undefined}>
                        <NavLink
                          to={l.to}
                          end={l.to === '/admin'}
                          className={({ isActive }) => `admin-nav-link${isActive ? ' active' : ''}`}
                          onClick={() => setOpen(false)}
                        >
                          <Icon size={18} />
                          <span>{t(l.label)}</span>
                        </NavLink>
                        {isSettings && !onSettings && (
                          <button
                            type="button"
                            className={`nav-tree-toggle${settingsExpanded ? ' open' : ''}`}
                            aria-expanded={settingsExpanded}
                            aria-controls="nav-settings-tree"
                            aria-label={t('nav.settingsSections')}
                            title={t('nav.settingsSections')}
                            onClick={() => setSettingsOpen((v) => !v)}
                          >
                            ▸
                          </button>
                        )}
                      </div>
                      {isSettings && settingsExpanded && (
                        <ul className="nav-subtree" id="nav-settings-tree">
                          {settingsSections.map((s) => (
                            <li key={s.id}>
                              <button
                                type="button"
                                className={`admin-nav-sublink${currentSection === s.id ? ' active' : ''}`}
                                onClick={() => { navigate(`/admin/settings?section=${s.id}`); setOpen(false); }}
                              >
                                {t(s.label)}
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <button className="btn-pos-launch" onClick={() => navigate('/pos')}>
            <IconShoppingCart size={16} />
            <span>{t('nav.openPos')}</span>
          </button>
          {user && (
            <div className="user-card">
              <span className="user-avatar">{initials(displayName)}</span>
              <div className="user-meta">
                <span className="user-name">{displayName}</span>
                <span className={`role-badge role-${user.role}`}>{t(`roles.${user.role}`)}</span>
              </div>
              <button
                className="btn-logout"
                onClick={() => navigate('/change-pin')}
                title={t('changePin.voluntary')}
                aria-label={t('changePin.voluntary')}
              >
                <IconSettings size={18} />
              </button>
              <button className="btn-logout" onClick={logout} title={t('nav.signOut')} aria-label={t('nav.signOut')}>
                <IconLogOut size={18} />
              </button>
            </div>
          )}
          <div className="sidebar-vendor">© {VENDOR_NAME}</div>
        </div>
      </aside>
    </>
  );
}
