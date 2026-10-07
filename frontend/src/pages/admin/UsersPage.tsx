// User management: list, create, edit, reset PIN.
import { useEffect, useState } from 'react';
import { getErrorMessage, httpClient } from '../../services/api/httpClient';
import type { PagedResponse, StoreOut, UserOut, UserRole } from '../../types/api';
import { AdminNav } from '../../components/admin/AdminNav';

const ROLES: UserRole[] = ['admin', 'manager', 'cashier'];

export function UsersPage() {
  const [users, setUsers] = useState<UserOut[]>([]);
  const [stores, setStores] = useState<StoreOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
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

  async function fetchUsers(p = page) {
    setLoading(true);
    setError('');
    try {
      const [usersResp, storesResp] = await Promise.all([
        httpClient.get<PagedResponse<UserOut>>('/users', { params: { page: p, per_page: 25 } }),
        httpClient.get<PagedResponse<StoreOut>>('/stores', { params: { per_page: 100 } }),
      ]);
      setUsers(usersResp.data.items);
      setTotal(usersResp.data.total);
      setStores(storesResp.data.items);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchUsers(); }, [page]);

  function openCreate() {
    setModal('create');
    setTarget(null);
    setFormUsername(''); setFormFullName(''); setFormPin('');
    setFormRole('cashier'); setFormStoreId(''); setFormActive(true); setFormError('');
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
        <h2>Users</h2>
        <div className="admin-actions">
          <button className="btn-primary" onClick={openCreate}>+ Add User</button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">Loading…</div>}

      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>Username</th><th>Full Name</th><th>Role</th><th>Active</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.username}</td>
                <td>{u.full_name}</td>
                <td><span className={`role-badge role-${u.role}`}>{u.role}</span></td>
                <td>{u.is_active ? '✓' : '—'}</td>
                <td className="table-actions">
                  <button className="btn-sm" onClick={() => openEdit(u)}>Edit</button>
                  <button className="btn-sm" onClick={() => openPin(u)}>Reset PIN</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</button>
        <span>Page {page} · {total} users</span>
        <button disabled={users.length < 25} onClick={() => setPage(page + 1)}>Next →</button>
      </div>

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            {modal === 'create' && (
              <>
                <h3>Add User</h3>
                {formError && <div className="form-error">{formError}</div>}
                <form onSubmit={handleCreate} className="modal-form">
                  <label className="field-label">Username
                    <input className="field-input" value={formUsername} onChange={e => setFormUsername(e.target.value)} required pattern="[a-z0-9_]+" minLength={3} maxLength={50} />
                  </label>
                  <label className="field-label">Full Name
                    <input className="field-input" value={formFullName} onChange={e => setFormFullName(e.target.value)} required />
                  </label>
                  <label className="field-label">PIN (4–8 digits)
                    <input className="field-input" type="password" inputMode="numeric" value={formPin} onChange={e => setFormPin(e.target.value)} required minLength={4} maxLength={8} />
                  </label>
                  <label className="field-label">Role
                    <select className="field-input" value={formRole} onChange={e => setFormRole(e.target.value as UserRole)}>
                      {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </label>
                  <label className="field-label">Store
                    <select className="field-input" value={formStoreId} onChange={e => setFormStoreId(e.target.value)}>
                      <option value="">— None —</option>
                      {stores.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  </label>
                  <div className="modal-buttons">
                    <button type="button" className="btn-secondary" onClick={() => setModal(null)}>Cancel</button>
                    <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Create'}</button>
                  </div>
                </form>
              </>
            )}

            {modal === 'edit' && target && (
              <>
                <h3>Edit {target.username}</h3>
                {formError && <div className="form-error">{formError}</div>}
                <form onSubmit={handleEdit} className="modal-form">
                  <label className="field-label">Full Name
                    <input className="field-input" value={formFullName} onChange={e => setFormFullName(e.target.value)} required />
                  </label>
                  <label className="field-label">Role
                    <select className="field-input" value={formRole} onChange={e => setFormRole(e.target.value as UserRole)}>
                      {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </label>
                  <label className="field-label">Store
                    <select className="field-input" value={formStoreId} onChange={e => setFormStoreId(e.target.value)}>
                      <option value="">— None —</option>
                      {stores.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  </label>
                  <label className="field-label checkbox-label">
                    <input type="checkbox" checked={formActive} onChange={e => setFormActive(e.target.checked)} />
                    Active
                  </label>
                  <div className="modal-buttons">
                    <button type="button" className="btn-secondary" onClick={() => setModal(null)}>Cancel</button>
                    <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
                  </div>
                </form>
              </>
            )}

            {modal === 'pin' && target && (
              <>
                <h3>Reset PIN — {target.username}</h3>
                {formError && <div className="form-error">{formError}</div>}
                <form onSubmit={handlePin} className="modal-form">
                  <label className="field-label">New PIN (4–8 digits)
                    <input className="field-input" type="password" inputMode="numeric" value={formPin} onChange={e => setFormPin(e.target.value)} required minLength={4} maxLength={8} />
                  </label>
                  <div className="modal-buttons">
                    <button type="button" className="btn-secondary" onClick={() => setModal(null)}>Cancel</button>
                    <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Reset PIN'}</button>
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
