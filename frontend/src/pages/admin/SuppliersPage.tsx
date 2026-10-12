// Supplier Management page — admin and manager.
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AdminNav } from '../../components/admin/AdminNav';
import { IconEdit, IconTruck, IconX } from '../../components/common/Icons';
import { supplierApi } from '../../services/api/supplierApi';
import type { SupplierCreatePayload, SupplierUpdatePayload } from '../../services/api/supplierApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { SupplierDashboard, SupplierOut } from '../../types/api';
import { formatDate } from '../../utils/format';

type StatusView = 'active' | 'inactive';

const PAYMENT_TERMS = ['immediate', 'net_7', 'net_15', 'net_30'] as const;

function StatCard({ label, value, accent }: { label: string; value: number; accent?: string }) {
  return (
    <div className="stat-card" style={{ borderTop: `3px solid ${accent ?? 'var(--color-primary)'}` }}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function emptyForm(): SupplierCreatePayload {
  return {
    supplier_code: '',
    company_name: '',
    contact_person: '',
    phone: '',
    alt_phone: '',
    email: '',
    gstin: '',
    pan: '',
    billing_address: '',
    city: '',
    state: '',
    pincode: '',
    country: 'India',
    payment_terms: 'net_30',
    notes: '',
  };
}

export function SuppliersPage() {
  const { t } = useTranslation();

  const [dash, setDash] = useState<SupplierDashboard | null>(null);
  const [items, setItems] = useState<SupplierOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [view, setView] = useState<StatusView>('active');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [modal, setModal] = useState<'add' | 'edit' | null>(null);
  const [target, setTarget] = useState<SupplierOut | null>(null);
  const [form, setForm] = useState<SupplierCreatePayload>(emptyForm());
  const [isActive, setIsActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [confirmActive, setConfirmActive] = useState(false);
  const [toggling, setToggling] = useState(false);

  const searchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const perPage = 20;

  async function loadDash() {
    try {
      const r = await supplierApi.dashboard();
      setDash(r.data);
    } catch {
      // non-critical; silently fail
    }
  }

  async function load(p = page, s = search, v = view) {
    setLoading(true);
    setError('');
    try {
      const r = await supplierApi.list({
        page: p,
        per_page: perPage,
        status: v,
        q: s || undefined,
      });
      setItems(r.data.items);
      setTotal(r.data.total);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDash();
  }, []);

  useEffect(() => {
    load(page, search, view);
  }, [page, view]);

  function handleSearchChange(v: string) {
    setSearch(v);
    if (searchTimeout.current) clearTimeout(searchTimeout.current);
    searchTimeout.current = setTimeout(() => {
      setPage(1);
      load(1, v, view);
    }, 350);
  }

  function openAdd() {
    setForm(emptyForm());
    setIsActive(true);
    setTarget(null);
    setFormError('');
    setModal('add');
  }

  function openEdit(s: SupplierOut) {
    setForm({
      supplier_code: s.supplier_code,
      company_name: s.company_name,
      contact_person: s.contact_person ?? '',
      phone: s.phone ?? '',
      alt_phone: s.alt_phone ?? '',
      email: s.email ?? '',
      gstin: s.gstin ?? '',
      pan: s.pan ?? '',
      billing_address: s.billing_address ?? '',
      city: s.city ?? '',
      state: s.state ?? '',
      pincode: s.pincode ?? '',
      country: s.country,
      payment_terms: s.payment_terms,
      notes: s.notes ?? '',
    });
    setIsActive(s.is_active);
    setTarget(s);
    setFormError('');
    setModal('edit');
  }

  function closeModal() {
    setModal(null);
    setTarget(null);
    setFormError('');
  }

  function field(key: keyof SupplierCreatePayload, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFormError('');
    const payload: SupplierCreatePayload = {
      ...form,
      supplier_code: form.supplier_code?.trim() || undefined,
      contact_person: form.contact_person?.trim() || undefined,
      phone: form.phone?.trim() || undefined,
      alt_phone: form.alt_phone?.trim() || undefined,
      email: form.email?.trim() || undefined,
      gstin: form.gstin?.trim() || undefined,
      pan: form.pan?.trim() || undefined,
      billing_address: form.billing_address?.trim() || undefined,
      city: form.city?.trim() || undefined,
      state: form.state?.trim() || undefined,
      pincode: form.pincode?.trim() || undefined,
      notes: form.notes?.trim() || undefined,
    };
    try {
      if (modal === 'add') {
        await supplierApi.create(payload);
      } else if (target) {
        const update: SupplierUpdatePayload = { ...payload, is_active: isActive };
        await supplierApi.update(target.id, update);
      }
      closeModal();
      await loadDash();
      setPage(1);
      await load(1, search, view);
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleToggleStatus() {
    if (confirmId === null) return;
    setToggling(true);
    try {
      await supplierApi.toggleStatus(confirmId);
      setConfirmId(null);
      await loadDash();
      await load(page, search, view);
    } catch (err) {
      setError(getErrorMessage(err));
      setConfirmId(null);
    } finally {
      setToggling(false);
    }
  }

  const emptyMsg = view === 'active' ? t('suppliers.emptyActive') : t('suppliers.emptyInactive');

  return (
    <div className="admin-page">
      <AdminNav />

      {/* Header */}
      <div className="admin-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <IconTruck size={22} />
          <h2>{t('suppliers.title')}</h2>
        </div>
        <button className="btn-primary" onClick={openAdd}>
          {t('suppliers.add')}
        </button>
      </div>

      {/* Dashboard cards */}
      {dash && (
        <div className="stats-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 20 }}>
          <StatCard label={t('suppliers.cardTotal')} value={dash.total} accent="var(--color-primary)" />
          <StatCard label={t('suppliers.cardActive')} value={dash.active} accent="var(--color-success)" />
          <StatCard label={t('suppliers.cardInactive')} value={dash.inactive} accent="var(--color-text-muted)" />
          <StatCard label={t('suppliers.cardProducts')} value={dash.products_linked} accent="var(--color-warning)" />
        </div>
      )}

      {/* Search + status filter */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        <input
          className="field-input"
          style={{ flex: 1, minWidth: 200 }}
          placeholder={t('suppliers.searchPlaceholder')}
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
        />
        <select
          className="field-input"
          style={{ width: 160 }}
          value={view}
          onChange={(e) => { setView(e.target.value as StatusView); setPage(1); }}
        >
          <option value="active">{t('common.active')}</option>
          <option value="inactive">{t('common.deactivated')}</option>
        </select>
      </div>

      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">{t('suppliers.loading')}</div>}

      {/* Status toggle confirm */}
      {confirmId !== null && (
        <div className="confirm-overlay">
          <div className="confirm-card">
            <p>{confirmActive ? t('suppliers.deactivateConfirm') : t('suppliers.reactivateConfirm')}</p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn-secondary" onClick={() => setConfirmId(null)} disabled={toggling}>
                {t('common.cancel')}
              </button>
              <button
                className={confirmActive ? 'btn-danger' : 'btn-primary'}
                onClick={handleToggleStatus}
                disabled={toggling}
              >
                {confirmActive ? t('suppliers.deactivateBtn') : t('suppliers.reactivateBtn')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t('suppliers.colCode')}</th>
              <th>{t('suppliers.colName')}</th>
              <th>{t('suppliers.colContact')}</th>
              <th>{t('suppliers.colPhone')}</th>
              <th>{t('suppliers.colEmail')}</th>
              <th>{t('suppliers.colGstin')}</th>
              <th style={{ textAlign: 'center' }}>{t('suppliers.colProducts')}</th>
              <th>{t('suppliers.colStatus')}</th>
              <th>{t('suppliers.colCreated')}</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.id}>
                <td><span style={{ fontFamily: 'monospace', fontSize: '0.85em' }}>{s.supplier_code}</span></td>
                <td><strong>{s.company_name}</strong></td>
                <td>{s.contact_person ?? '—'}</td>
                <td>{s.phone ?? '—'}</td>
                <td style={{ fontSize: '0.88em' }}>{s.email ?? '—'}</td>
                <td style={{ fontFamily: 'monospace', fontSize: '0.85em' }}>{s.gstin ?? '—'}</td>
                <td style={{ textAlign: 'center' }}>{s.product_count}</td>
                <td>
                  <span className={`status-badge ${s.is_active ? 'badge-success' : 'badge-neutral'}`}>
                    {s.is_active ? t('common.active') : t('common.deactivated')}
                  </span>
                </td>
                <td style={{ whiteSpace: 'nowrap' }}>{formatDate(s.created_at)}</td>
                <td>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button
                      className="btn-icon"
                      title={t('suppliers.editBtn')}
                      onClick={() => openEdit(s)}
                    >
                      <IconEdit size={15} />
                    </button>
                    <button
                      className={`btn-icon ${s.is_active ? 'btn-icon-danger' : ''}`}
                      title={s.is_active ? t('suppliers.deactivateBtn') : t('suppliers.reactivateBtn')}
                      onClick={() => { setConfirmId(s.id); setConfirmActive(s.is_active); }}
                    >
                      <IconX size={15} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {items.length === 0 && !loading && (
              <tr>
                <td colSpan={10} className="empty-row">{emptyMsg}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="pagination">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>{t('common.prev')}</button>
        <span>{t('common.pageInfo', { page, total })}</span>
        <button disabled={items.length < perPage} onClick={() => setPage(page + 1)}>{t('common.next')}</button>
      </div>

      {/* Add / Edit modal */}
      {modal && (
        <div className="modal-overlay" onClick={closeModal}>
          <div
            className="modal-box"
            style={{ maxWidth: 640, width: '95%', maxHeight: '90vh', overflowY: 'auto' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ marginBottom: 16 }}>
              {modal === 'add' ? t('suppliers.addTitle') : t('suppliers.editTitle', { name: target?.company_name })}
            </h3>
            <form onSubmit={handleSave} className="modal-form">

              {/* Section 1: Basic */}
              <div className="form-section-title">{t('suppliers.sectionBasic')}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
                <label className="field-label">
                  {t('suppliers.fieldCode')}
                  <span style={{ fontSize: '0.8em', color: 'var(--color-text-muted)', marginLeft: 6 }}>
                    {t('suppliers.fieldCodeHint')}
                  </span>
                  <input
                    className="field-input"
                    value={form.supplier_code ?? ''}
                    onChange={(e) => field('supplier_code', e.target.value)}
                    placeholder="e.g. SUP-ABC123"
                    disabled={modal === 'edit'}
                  />
                </label>
                <label className="field-label">
                  {t('suppliers.fieldName')} <span style={{ color: 'var(--color-danger)' }}>*</span>
                  <input
                    className="field-input"
                    required
                    value={form.company_name}
                    onChange={(e) => field('company_name', e.target.value)}
                    placeholder="e.g. ABC Traders Pvt Ltd"
                  />
                </label>
                <label className="field-label">
                  {t('suppliers.fieldContact')}
                  <input
                    className="field-input"
                    value={form.contact_person ?? ''}
                    onChange={(e) => field('contact_person', e.target.value)}
                    placeholder="e.g. Ramesh Patil"
                  />
                </label>
                <label className="field-label">
                  {t('suppliers.fieldPhone')}
                  <input
                    className="field-input"
                    value={form.phone ?? ''}
                    onChange={(e) => field('phone', e.target.value)}
                    placeholder="e.g. 9876543210"
                  />
                </label>
                <label className="field-label">
                  {t('suppliers.fieldAltPhone')}
                  <input
                    className="field-input"
                    value={form.alt_phone ?? ''}
                    onChange={(e) => field('alt_phone', e.target.value)}
                  />
                </label>
                <label className="field-label">
                  {t('suppliers.fieldEmail')}
                  <input
                    className="field-input"
                    type="email"
                    value={form.email ?? ''}
                    onChange={(e) => field('email', e.target.value)}
                    placeholder="e.g. supplier@example.com"
                  />
                </label>
              </div>

              {/* Section 2: Business */}
              <div className="form-section-title" style={{ marginTop: 16 }}>{t('suppliers.sectionBusiness')}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
                <label className="field-label">
                  {t('suppliers.fieldGstin')}
                  <input
                    className="field-input"
                    value={form.gstin ?? ''}
                    onChange={(e) => field('gstin', e.target.value.toUpperCase())}
                    placeholder="e.g. 27AAPFU0939F1ZV"
                    maxLength={15}
                  />
                </label>
                <label className="field-label">
                  {t('suppliers.fieldPan')}
                  <input
                    className="field-input"
                    value={form.pan ?? ''}
                    onChange={(e) => field('pan', e.target.value.toUpperCase())}
                    placeholder="e.g. AAPFU0939F"
                    maxLength={10}
                  />
                </label>
                <label className="field-label" style={{ gridColumn: '1 / -1' }}>
                  {t('suppliers.fieldAddress')}
                  <textarea
                    className="field-input"
                    rows={2}
                    value={form.billing_address ?? ''}
                    onChange={(e) => field('billing_address', e.target.value)}
                  />
                </label>
                <label className="field-label">
                  {t('suppliers.fieldCity')}
                  <input
                    className="field-input"
                    value={form.city ?? ''}
                    onChange={(e) => field('city', e.target.value)}
                  />
                </label>
                <label className="field-label">
                  {t('suppliers.fieldState')}
                  <input
                    className="field-input"
                    value={form.state ?? ''}
                    onChange={(e) => field('state', e.target.value)}
                  />
                </label>
                <label className="field-label">
                  {t('suppliers.fieldPincode')}
                  <input
                    className="field-input"
                    value={form.pincode ?? ''}
                    onChange={(e) => field('pincode', e.target.value)}
                    maxLength={10}
                  />
                </label>
                <label className="field-label">
                  {t('suppliers.fieldCountry')}
                  <input
                    className="field-input"
                    value={form.country ?? 'India'}
                    onChange={(e) => field('country', e.target.value)}
                  />
                </label>
              </div>

              {/* Section 3: Additional */}
              <div className="form-section-title" style={{ marginTop: 16 }}>{t('suppliers.sectionExtra')}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
                <label className="field-label">
                  {t('suppliers.fieldPaymentTerms')}
                  <select
                    className="field-input"
                    value={form.payment_terms ?? 'net_30'}
                    onChange={(e) => field('payment_terms', e.target.value)}
                  >
                    {PAYMENT_TERMS.map((pt) => (
                      <option key={pt} value={pt}>{t(`suppliers.terms.${pt}`)}</option>
                    ))}
                  </select>
                </label>
                {modal === 'edit' && (
                  <label className="field-label" style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 8, paddingTop: 22 }}>
                    <input
                      type="checkbox"
                      checked={isActive}
                      onChange={(e) => setIsActive(e.target.checked)}
                    />
                    {t('suppliers.fieldActive')}
                  </label>
                )}
                <label className="field-label" style={{ gridColumn: '1 / -1' }}>
                  {t('suppliers.fieldNotes')}
                  <textarea
                    className="field-input"
                    rows={2}
                    value={form.notes ?? ''}
                    onChange={(e) => field('notes', e.target.value)}
                  />
                </label>
              </div>

              {formError && <div className="page-error" style={{ marginTop: 10 }}>{formError}</div>}

              <div className="modal-buttons" style={{ marginTop: 16 }}>
                <button type="button" className="btn-secondary" onClick={closeModal} disabled={saving}>
                  {t('common.cancel')}
                </button>
                <button type="submit" className="btn-primary" disabled={saving}>
                  {saving ? t('common.saving') : t('common.save')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
