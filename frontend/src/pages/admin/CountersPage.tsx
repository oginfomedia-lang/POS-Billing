// Store and counter management. Admins edit; managers can view.
// A counter's code must match "counterCode" in counter.json on that till's PC.
import { type FormEvent, useEffect, useState } from 'react';
import { AdminNav } from '../../components/admin/AdminNav';
import { useAuth } from '../../hooks/useAuth';
import { getErrorMessage } from '../../services/api/httpClient';
import {
  createCounter,
  createStore,
  listCounters,
  listStores,
  updateCounter,
  updateStore,
} from '../../services/api/storeApi';
import type { CounterOut, StoreOut } from '../../types/api';

type Modal =
  | { kind: 'store'; store: StoreOut | null }
  | { kind: 'counter'; counter: CounterOut | null }
  | null;

export function CountersPage() {
  const { isAdmin } = useAuth();

  const [stores, setStores] = useState<StoreOut[]>([]);
  const [selected, setSelected] = useState<StoreOut | null>(null);
  const [counters, setCounters] = useState<CounterOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [modal, setModal] = useState<Modal>(null);
  const [form, setForm] = useState({ name: '', address: '', phone: '', gstin: '', code: '', label: '', active: true });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  async function fetchStores(keepId?: number) {
    setLoading(true);
    setError('');
    try {
      const list = await listStores();
      setStores(list);
      setSelected(list.find((s) => s.id === (keepId ?? selected?.id)) ?? list[0] ?? null);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function fetchCounters(storeId: number) {
    try {
      setCounters(await listCounters(storeId));
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  useEffect(() => { fetchStores(); }, []);
  useEffect(() => {
    if (selected) fetchCounters(selected.id);
    else setCounters([]);
  }, [selected?.id]);

  function openStore(store: StoreOut | null) {
    setForm({
      ...form,
      name: store?.name ?? '',
      address: store?.address ?? '',
      phone: store?.phone ?? '',
      gstin: store?.gstin ?? '',
      active: store?.is_active ?? true,
    });
    setFormError('');
    setModal({ kind: 'store', store });
  }

  function openCounter(counter: CounterOut | null) {
    setForm({ ...form, code: counter?.code ?? '', label: counter?.label ?? '', active: counter?.is_active ?? true });
    setFormError('');
    setModal({ kind: 'counter', counter });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!modal) return;
    setSaving(true);
    setFormError('');
    try {
      if (modal.kind === 'store') {
        const data = {
          name: form.name.trim(),
          address: form.address.trim() || null,
          phone: form.phone.trim() || null,
          gstin: form.gstin.trim() || null,
        };
        const saved = modal.store
          ? await updateStore(modal.store.id, { ...data, is_active: form.active })
          : await createStore(data);
        await fetchStores(saved.id);
      } else if (selected) {
        if (modal.counter) {
          await updateCounter(selected.id, modal.counter.id, { label: form.label.trim(), is_active: form.active });
        } else {
          await createCounter(selected.id, form.code.trim().toUpperCase(), form.label.trim());
        }
        await fetchCounters(selected.id);
      }
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
        <h2>Stores &amp; Counters</h2>
        {isAdmin && (
          <div className="admin-actions">
            <button className="btn-primary" onClick={() => openStore(null)}>+ Add Store</button>
          </div>
        )}
      </div>

      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">Loading…</div>}

      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr><th>Store</th><th>Address</th><th>Phone</th><th>GSTIN</th><th>Active</th><th /></tr>
          </thead>
          <tbody>
            {!loading && stores.length === 0 && (
              <tr><td colSpan={6} className="empty-row">No stores yet. Add one to get started.</td></tr>
            )}
            {stores.map((s) => (
              <tr
                key={s.id}
                className={`clickable-row${selected?.id === s.id ? ' selected-row' : ''}`}
                onClick={() => setSelected(s)}
              >
                <td>{s.name}</td>
                <td>{s.address ?? '—'}</td>
                <td>{s.phone ?? '—'}</td>
                <td>{s.gstin ?? '—'}</td>
                <td>{s.is_active ? '✓' : '—'}</td>
                <td className="table-actions">
                  {isAdmin && (
                    <button className="btn-sm" onClick={(e) => { e.stopPropagation(); openStore(s); }}>Edit</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && (
        <section className="sub-section">
          <div className="admin-header">
            <h3>Counters — {selected.name}</h3>
            {isAdmin && (
              <div className="admin-actions">
                <button className="btn-primary" onClick={() => openCounter(null)}>+ Add Counter</button>
              </div>
            )}
          </div>
          <p className="hint-text">
            Each till PC's <code>counter.json</code> must have <code>"counterCode"</code> set to one of these codes,
            or cashiers on that PC can't open a shift.
          </p>
          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr><th>Code</th><th>Label</th><th>Active</th><th /></tr>
              </thead>
              <tbody>
                {counters.length === 0 && (
                  <tr><td colSpan={4} className="empty-row">No counters in this store.</td></tr>
                )}
                {counters.map((c) => (
                  <tr key={c.id}>
                    <td><strong>{c.code}</strong></td>
                    <td>{c.label}</td>
                    <td>{c.is_active ? '✓' : '—'}</td>
                    <td className="table-actions">
                      {isAdmin && <button className="btn-sm" onClick={() => openCounter(c)}>Edit</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3>
              {modal.kind === 'store'
                ? (modal.store ? `Edit ${modal.store.name}` : 'Add Store')
                : (modal.counter ? `Edit Counter ${modal.counter.code}` : `Add Counter — ${selected?.name}`)}
            </h3>
            {formError && <div className="form-error">{formError}</div>}
            <form onSubmit={handleSubmit} className="modal-form">
              {modal.kind === 'store' ? (
                <>
                  <label className="field-label">Name
                    <input className="field-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required maxLength={150} autoFocus />
                  </label>
                  <label className="field-label">Address
                    <input className="field-input" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
                  </label>
                  <label className="field-label">Phone
                    <input className="field-input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} maxLength={20} />
                  </label>
                  <label className="field-label">GSTIN
                    <input className="field-input" value={form.gstin} onChange={(e) => setForm({ ...form, gstin: e.target.value })} maxLength={20} />
                  </label>
                </>
              ) : (
                <>
                  <label className="field-label">Code (e.g. C02)
                    <input
                      className="field-input"
                      value={form.code}
                      onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
                      required
                      pattern="[A-Z0-9]+"
                      maxLength={10}
                      disabled={modal.counter !== null}
                      title="Letters and digits only. Can't be changed later."
                      autoFocus={modal.counter === null}
                    />
                  </label>
                  <label className="field-label">Label
                    <input className="field-input" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} required maxLength={100} placeholder="e.g. Counter 2 (near entrance)" />
                  </label>
                </>
              )}
              {(modal.kind === 'store' ? modal.store : modal.counter) && (
                <label className="field-label checkbox-label">
                  <input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} />
                  Active
                </label>
              )}
              <div className="modal-buttons">
                <button type="button" className="btn-secondary" onClick={() => setModal(null)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
