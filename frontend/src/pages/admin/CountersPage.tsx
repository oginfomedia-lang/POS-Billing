// Store and counter management. Admins edit; managers can view.
// A counter's code must match "counterCode" in counter.json on that till's PC.
import { type FormEvent, useEffect, useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { AdminNav } from '../../components/admin/AdminNav';
import { StatusTabs, type StatusView } from '../../components/admin/StatusTabs';
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
import { useStoreContext } from '../../store/storeContext';

type Modal =
  | { kind: 'store'; store: StoreOut | null }
  | { kind: 'counter'; counter: CounterOut | null }
  | null;

export function CountersPage() {
  const { t } = useTranslation();
  const { isAdmin } = useAuth();

  const [stores, setStores] = useState<StoreOut[]>([]);
  const [selected, setSelected] = useState<StoreOut | null>(null);
  const [counters, setCounters] = useState<CounterOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  // Active and deactivated stores / counters are listed separately.
  const [storeView, setStoreView] = useState<StatusView>('active');
  const [counterView, setCounterView] = useState<StatusView>('active');

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

  const visibleStores = stores.filter((s) => s.is_active === (storeView === 'active'));
  const visibleCounters = counters.filter((c) => c.is_active === (counterView === 'active'));
  const storeCounts = { active: stores.filter((s) => s.is_active).length, inactive: stores.filter((s) => !s.is_active).length };
  const counterCounts = { active: counters.filter((c) => c.is_active).length, inactive: counters.filter((c) => !c.is_active).length };

  // Keep the selected store inside the tab being shown (e.g. after deactivating it or switching tabs).
  useEffect(() => {
    if (!visibleStores.some((s) => s.id === selected?.id)) setSelected(visibleStores[0] ?? null);
  }, [storeView, stores]);
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
        await useStoreContext.getState().refresh();
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
        <h2>{t('stores.title')}</h2>
        {isAdmin && (
          <div className="admin-actions">
            <button className="btn-primary" onClick={() => openStore(null)}>{t('stores.addStore')}</button>
          </div>
        )}
      </div>

      {error && <div className="page-error">{error}</div>}
      <StatusTabs value={storeView} onChange={setStoreView} counts={storeCounts} />
      {loading && <div className="loading-text">{t('common.loading')}</div>}

      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr><th>{t('stores.colStore')}</th><th>{t('stores.colAddress')}</th><th>{t('stores.colPhone')}</th><th>{t('stores.colGstin')}</th><th /></tr>
          </thead>
          <tbody>
            {!loading && visibleStores.length === 0 && (
              <tr>
                <td colSpan={5} className="empty-row">
                  {storeView === 'inactive'
                    ? t('stores.emptyInactive')
                    : stores.length === 0 ? t('stores.emptyNone') : t('stores.emptyActive')}
                </td>
              </tr>
            )}
            {visibleStores.map((s) => (
              <tr
                key={s.id}
                className={`clickable-row${selected?.id === s.id ? ' selected-row' : ''}`}
                onClick={() => setSelected(s)}
              >
                <td>{s.name}</td>
                <td>{s.address ?? '—'}</td>
                <td>{s.phone ?? '—'}</td>
                <td>{s.gstin ?? '—'}</td>
                <td className="table-actions">
                  {isAdmin && (
                    <button className="btn-sm" onClick={(e) => { e.stopPropagation(); openStore(s); }}>{t('common.edit')}</button>
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
            <h3>{t('stores.countersTitle', { store: selected.name })}</h3>
            {isAdmin && (
              <div className="admin-actions">
                <button className="btn-primary" onClick={() => openCounter(null)}>{t('stores.addCounter')}</button>
              </div>
            )}
          </div>
          <p className="hint-text">
            <Trans i18nKey="stores.counterHint" components={{ code: <code /> }} />
          </p>
          <StatusTabs value={counterView} onChange={setCounterView} counts={counterCounts} />
          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr><th>{t('stores.colCode')}</th><th>{t('stores.colLabel')}</th><th /></tr>
              </thead>
              <tbody>
                {visibleCounters.length === 0 && (
                  <tr>
                    <td colSpan={3} className="empty-row">
                      {counterView === 'active' ? t('stores.emptyCountersActive') : t('stores.emptyCountersInactive')}
                    </td>
                  </tr>
                )}
                {visibleCounters.map((c) => (
                  <tr key={c.id}>
                    <td><strong>{c.code}</strong></td>
                    <td>{c.label}</td>
                    <td className="table-actions">
                      {isAdmin && <button className="btn-sm" onClick={() => openCounter(c)}>{t('common.edit')}</button>}
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
                ? (modal.store ? t('stores.editStore', { name: modal.store.name }) : t('stores.addStoreTitle'))
                : (modal.counter ? t('stores.editCounter', { code: modal.counter.code }) : t('stores.addCounterTitle', { store: selected?.name }))}
            </h3>
            {formError && <div className="form-error">{formError}</div>}
            <form onSubmit={handleSubmit} className="modal-form">
              {modal.kind === 'store' ? (
                <>
                  <label className="field-label">{t('common.name')}
                    <input className="field-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required maxLength={150} autoFocus />
                  </label>
                  <label className="field-label">{t('stores.address')}
                    <input className="field-input" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
                  </label>
                  <label className="field-label">{t('stores.phone')}
                    <input className="field-input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} maxLength={20} />
                  </label>
                  <label className="field-label">{t('stores.gstin')}
                    <input className="field-input" value={form.gstin} onChange={(e) => setForm({ ...form, gstin: e.target.value })} maxLength={20} />
                  </label>
                </>
              ) : (
                <>
                  <label className="field-label">{t('stores.code')}
                    <input
                      className="field-input"
                      value={form.code}
                      onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
                      required
                      pattern="[A-Z0-9]+"
                      maxLength={10}
                      disabled={modal.counter !== null}
                      title={t('stores.codeTitle')}
                      autoFocus={modal.counter === null}
                    />
                  </label>
                  <label className="field-label">{t('stores.label')}
                    <input className="field-input" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} required maxLength={100} placeholder={t('stores.labelPlaceholder')} />
                  </label>
                </>
              )}
              {(modal.kind === 'store' ? modal.store : modal.counter) && (
                <label className="field-label checkbox-label">
                  <input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} />
                  {t('common.active')}
                </label>
              )}
              <div className="modal-buttons">
                <button type="button" className="btn-secondary" onClick={() => setModal(null)}>{t('common.cancel')}</button>
                <button type="submit" className="btn-primary" disabled={saving}>{saving ? t('common.saving') : t('common.save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
