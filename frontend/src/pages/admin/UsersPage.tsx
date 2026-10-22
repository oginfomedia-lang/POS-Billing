// User management: list, create, edit, reset PIN.
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getErrorMessage, httpClient } from '../../services/api/httpClient';
import type { PagedResponse, StoreOut, UserOut, UserRole } from '../../types/api';
import { AdminNav } from '../../components/admin/AdminNav';
import { MarathiInput } from '../../components/common/MarathiInput';
import { StatusTabs, type StatusView } from '../../components/admin/StatusTabs';
import { useStoreContext } from '../../store/storeContext';

const ROLES: UserRole[] = ['admin', 'manager', 'cashier'];

export function UsersPage() {
  const { t } = useTranslation();
  const [users, setUsers] = useState<UserOut[]>([]);
  const [stores, setStores] = useState<StoreOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  // Active and deactivated users are listed separately.
  const [view, setView] = useState<StatusView>('active');
  // Branch picked in the sidebar (null = all branches, head office).
  const branchId = useStoreContext((s) => s.selectedId);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Create / edit modal state
  const [modal, setModal] = useState<'create' | 'edit' | 'pin' | null>(null);
  const [target, setTarget] = useState<UserOut | null>(null);
  const [formUsername, setFormUsername] = useState('');
  const [formFullName, setFormFullName] = useState('');
  const [formPin, setFormPin] = useState('');
  const [formRole, setFormRole] = useState<UserRole>('cashier');
  const [formStoreId, setFormStoreId] = useState('');
  const [formActive, setFormActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  // Only the latest request may fill the table (switching branch quickly must not show the old branch's staff).
  const requestNo = useRef(0);

  async function fetchUsers(p = page) {
    const mine = ++requestNo.current;
    setLoading(true);
    setError('');
    try {
      const [usersResp, storesResp] = await Promise.all([
        httpClient.get<PagedResponse<UserOut>>('/users', { params: { page: p, per_page: 25, status: view, store_id: branchId ?? undefined } }),
        httpClient.get<PagedResponse<StoreOut>>('/stores', { params: { per_page: 100 } }),
      ]);
      if (mine !== requestNo.current) return;
      setUsers(usersResp.data.items);
      setTotal(usersResp.data.total);
      setStores(storesResp.data.items);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchUsers(); }, [page, view, branchId]);
  // A different branch starts again at page 1 with an empty table (no stale rows while loading).
  useEffect(() => { setPage(1); setUsers([]); }, [branchId]);

  const storeName = (id: number | null) =>
    id === null ? t('users.headOffice') : stores.find((s) => s.id === id)?.name ?? `#${id}`;
  // Managers and cashiers belong to one store; only admins may be head office (no store).
  const needsStore = formRole !== 'admin';
  // New staff only go to active stores; when editing, the person's current store stays in the list.
  const storeChoices = stores.filter((s) => s.is_active || String(s.id) === formStoreId);

  function openCreate() {
    setModal('create');
    setTarget(null);
    setFormUsername(''); setFormFullName(''); setFormPin('');
    setFormRole('cashier'); setFormStoreId(branchId === null ? '' : String(branchId)); setFormActive(true); setFormError('');
  }

  function openEdit(u: UserOut) {
    setModal('edit');
    setTarget(u);
    setFormFullName(u.full_name);
    setFormRole(u.role);
    setFormStoreId(u.store_id ? String(u.store_id) : '');
    setFormActive(u.is_active);
    setFormError('');
  }

  function openPin(u: UserOut) {
    setModal('pin');
    setTarget(u);
    setFormPin('');
    setFormError('');
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true); setFormError('');
    try {
      await httpClient.post('/users', {
        username: formUsername,
        full_name: formFullName,
        pin: formPin,
        role: formRole,
        store_id: formStoreId ? parseInt(formStoreId) : null,
      });
      setModal(null);
      fetchUsers();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!target) return;
    setSaving(true); setFormError('');
    try {
      await httpClient.put(`/users/${target.id}`, {
        full_name: formFullName,
        role: formRole,
        is_active: formActive,
        store_id: formStoreId ? parseInt(formStoreId) : null,
      });
      setModal(null);
      fetchUsers();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handlePin(e: React.FormEvent) {
    e.preventDefault();
    if (!target) return;
    setSaving(true); setFormError('');
    try {
      await httpClient.post(`/users/${target.id}/reset-pin`, { new_pin: formPin });
      setModal(null);
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="admin-page">
      <AdminNav />
      <div className="admin-header">
        <h2>{t('users.title')}</h2>
        <div className="admin-actions">
          <button className="btn-primary" onClick={openCreate}>{t('users.add')}</button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      <StatusTabs value={view} onChange={(v) => { setView(v); setPage(1); }} />
      {loading && <div className="loading-text">{t('common.loading')}</div>}

      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t('users.colUsername')}</th><th>{t('users.colFullName')}</th><th>{t('users.colRole')}</th><th>{t('users.colStore')}</th><th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {!loading && users.length === 0 && (
              <tr><td colSpan={5} className="empty-row">{view === 'active' ? t('users.emptyActive') : t('users.emptyInactive')}</td></tr>
            )}
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.username}</td>
                <td>{u.full_name}</td>
                <td><span className={`role-badge role-${u.role}`}>{t(`roles.${u.role}`)}</span></td>
                <td>{storeName(u.store_id)}</td>
                <td className="table-actions">
                  <button className="btn-sm" onClick={() => openEdit(u)}>{t('common.edit')}</button>
                  <button className="btn-sm" onClick={() => openPin(u)}>{t('users.resetPin')}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>{t('common.prev')}</button>
        <span>{t('common.pageInfo', { page, total })}</span>
        <button disabled={users.length < 25} onClick={() => setPage(page + 1)}>{t('common.next')}</button>
      </div>

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            {modal === 'create' && (
              <>
                <h3>{t('users.addTitle')}</h3>
                {formError && <div className="form-error">{formError}</div>}
                <form onSubmit={handleCreate} className="modal-form">
                  <label className="field-label">{t('users.username')}
                    <input className="field-input" value={formUsername} onChange={e => setFormUsername(e.target.value)} required pattern="[a-z0-9_]+" minLength={3} maxLength={50} />
                    <span className="hint-text">{t('users.usernameHint')}</span>
                  </label>
                  <label className="field-label">{t('users.fullName')}
                    <MarathiInput className="field-input" value={formFullName} onChange={setFormFullName} required maxLength={150} />
                  </label>
                  <label className="field-label">{t('users.pin')}
                    <input className="field-input" type="password" value={formPin} onChange={e => setFormPin(e.target.value)} required minLength={4} maxLength={12} />
                  </label>
                  <label className="field-label">{t('users.role')}
                    <select className="field-input" value={formRole} onChange={e => setFormRole(e.target.value as UserRole)}>
                      {ROLES.map(r => <option key={r} value={r}>{t(`roles.${r}`)}</option>)}
                    </select>
                  </label>
                  <label className="field-label">{t('common.store')}
                    <select className="field-input" value={formStoreId} onChange={e => setFormStoreId(e.target.value)} required={needsStore}>
                      <option value="" disabled={needsStore}>{needsStore ? t('users.chooseStore') : t('users.headOffice')}</option>
                      {storeChoices.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                    {needsStore && !formStoreId && <span className="hint-text">{t('users.storeRequired')}</span>}
                  </label>
                  <div className="modal-buttons">
                    <button type="button" className="btn-secondary" onClick={() => setModal(null)}>{t('common.cancel')}</button>
                    <button type="submit" className="btn-primary" disabled={saving}>{saving ? t('common.saving') : t('common.create')}</button>
                  </div>
                </form>
              </>
            )}

            {modal === 'edit' && target && (
              <>
                <h3>{t('users.editTitle', { name: target.username })}</h3>
                {formError && <div className="form-error">{formError}</div>}
                <form onSubmit={handleEdit} className="modal-form">
                  <label className="field-label">{t('users.fullName')}
                    <MarathiInput className="field-input" value={formFullName} onChange={setFormFullName} required maxLength={150} />
                  </label>
                  <label className="field-label">{t('users.role')}
                    <select className="field-input" value={formRole} onChange={e => setFormRole(e.target.value as UserRole)}>
                      {ROLES.map(r => <option key={r} value={r}>{t(`roles.${r}`)}</option>)}
                    </select>
                  </label>
                  <label className="field-label">{t('common.store')}
                    <select className="field-input" value={formStoreId} onChange={e => setFormStoreId(e.target.value)} required={needsStore}>
                      <option value="" disabled={needsStore}>{needsStore ? t('users.chooseStore') : t('users.headOffice')}</option>
                      {storeChoices.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                    {needsStore && !formStoreId && <span className="hint-text">{t('users.storeRequired')}</span>}
                  </label>
                  <label className="field-label checkbox-label">
                    <input type="checkbox" checked={formActive} onChange={e => setFormActive(e.target.checked)} />
                    {t('common.active')}
                  </label>
                  <div className="modal-buttons">
                    <button type="button" className="btn-secondary" onClick={() => setModal(null)}>{t('common.cancel')}</button>
                    <button type="submit" className="btn-primary" disabled={saving}>{saving ? t('common.saving') : t('common.save')}</button>
                  </div>
                </form>
              </>
            )}

            {modal === 'pin' && target && (
              <>
                <h3>{t('users.resetTitle', { name: target.username })}</h3>
                {formError && <div className="form-error">{formError}</div>}
                <form onSubmit={handlePin} className="modal-form">
                  <label className="field-label">{t('users.newPin')}
                    <input className="field-input" type="password" value={formPin} onChange={e => setFormPin(e.target.value)} required minLength={4} maxLength={12} />
                  </label>
                  <div className="modal-buttons">
                    <button type="button" className="btn-secondary" onClick={() => setModal(null)}>{t('common.cancel')}</button>
                    <button type="submit" className="btn-primary" disabled={saving}>{saving ? t('common.saving') : t('users.resetPin')}</button>
                  </div>
                </form>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
