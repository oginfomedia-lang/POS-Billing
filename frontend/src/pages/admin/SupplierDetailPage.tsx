// Supplier detail page — tabbed view: Overview, Products, POs, GRNs, Invoices, Payments, Ledger.
// The admin enters the supplier's bills (Invoices) and pays against them (Payments); what is owed is
// never more than the goods actually received (GRNs).
import React, { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { AdminNav } from '../../components/admin/AdminNav';
import { SupplierInvoiceDialog } from '../../components/admin/SupplierInvoiceDialog';
import { SupplierInvoiceEditDialog } from '../../components/admin/SupplierInvoiceEditDialog';
import { SupplierPaymentDialog } from '../../components/admin/SupplierPaymentDialog';
import {
  IconArrowLeft,
  IconTruck,
  IconClipboardList,
  IconFileText,
  IconTrash,
  IconPlus,
  IconDownload,
  IconPackage,
  IconSearch,
  IconAlert,
  IconCreditCard,
  IconCash,
  IconCheck,
  IconEdit,
  IconStore,
  IconUsers,
  IconHistory,
} from '../../components/common/Icons';
import { supplierApi } from '../../services/api/supplierApi';
import { supplierInvoiceApi } from '../../services/api/supplierInvoiceApi';
import { supplierPaymentApi } from '../../services/api/supplierPaymentApi';
import { purchaseApi } from '../../services/api/purchaseApi';
import { uploadApi } from '../../services/api/uploadApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type {
  SupplierOut,
  SupplierSummary,
  SupplierLedgerEntry,
  SupplierProductOut,
  PurchaseOrderOut,
  SupplierGRNOut,
  GoodsReceiptOut,
  SupplierInvoiceOut,
  SupplierPaymentOut,
  SupplierDocumentOut,
} from '../../types/api';
import { formatDate, formatCurrency } from '../../utils/format';

type Tab = 'overview' | 'products' | 'pos' | 'grns' | 'invoices' | 'payments' | 'ledger';

const TABS: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'products', label: 'Products' },
  { key: 'pos', label: 'Purchase Orders' },
  { key: 'grns', label: 'GRNs' },
  { key: 'invoices', label: 'Invoices' },
  { key: 'payments', label: 'Payments' },
  { key: 'ledger', label: 'Ledger' },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function InfoRow({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div style={{ display: 'flex', gap: 12, padding: '6px 0', borderBottom: '1px solid var(--color-border)' }}>
      <span style={{ minWidth: 160, color: 'var(--color-text-muted)', fontSize: '0.88em' }}>{label}</span>
      <span style={{ fontWeight: 500 }}>{value ?? '—'}</span>
    </div>
  );
}

function AmountBadge({ label, amount, variant, icon }: { label: string; amount: string | number; variant?: 'danger' | 'success' | 'warning' | 'info' | 'neutral'; icon?: React.ReactNode }) {
  const palette = {
    neutral: { cardBg: '#eff6ff', iconBg: '#dbeafe', iconColor: '#2563eb', text: '#1e3a8a', label: '#60a5fa' },
    success: { cardBg: '#f0fdf4', iconBg: '#dcfce7', iconColor: '#16a34a', text: '#14532d', label: '#4ade80' },
    info:    { cardBg: '#eef2ff', iconBg: '#e0e7ff', iconColor: '#4f46e5', text: '#312e81', label: '#818cf8' },
    warning: { cardBg: '#fff7ed', iconBg: '#fed7aa', iconColor: '#ea580c', text: '#7c2d12', label: '#fb923c' },
    danger:  { cardBg: '#fef2f2', iconBg: '#fecaca', iconColor: '#dc2626', text: '#7f1d1d', label: '#f87171' },
  };
  const p = palette[variant ?? 'neutral'];
  return (
    <div style={{ background: p.cardBg, border: `1px solid ${p.iconBg}`, borderRadius: 14, padding: '16px 16px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ width: 40, height: 40, borderRadius: 10, background: p.iconBg, display: 'flex', alignItems: 'center', justifyContent: 'center', color: p.iconColor }}>
        {icon}
      </div>
      <div>
        <div style={{ fontSize: '0.7em', color: p.label, marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.6px', fontWeight: 700 }}>{label}</div>
        <div style={{ fontSize: '1.3em', fontWeight: 700, color: p.text, letterSpacing: '-0.5px', whiteSpace: 'nowrap' }}>{formatCurrency(Number(amount))}</div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function SupplierDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const supplierId = Number(id);

  // ?tab=invoices opens a tab directly (e.g. from a purchase order).
  const [searchParams] = useSearchParams();
  const initialTab = TABS.some((t) => t.key === searchParams.get('tab')) ? (searchParams.get('tab') as Tab) : 'overview';
  const [tab, setTab] = useState<Tab>(initialTab);
  const [supplier, setSupplier] = useState<SupplierOut | null>(null);
  const [summary, setSummary] = useState<SupplierSummary | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  // Tab data
  const [products, setProducts] = useState<SupplierProductOut[]>([]);
  const [pos, setPos] = useState<PurchaseOrderOut[]>([]);
  const [grns, setGrns] = useState<SupplierGRNOut[]>([]);
  // Add-invoice / record-payment dialogs (undefined = closed; a number = preselected GRN / invoice).
  const [invoiceDialog, setInvoiceDialog] = useState<{ grnId?: number } | null>(null);
  const [paymentDialog, setPaymentDialog] = useState<{ invoiceId?: number; advance?: SupplierPaymentOut } | null>(null);
  const [editInvoice, setEditInvoice] = useState<SupplierInvoiceOut | null>(null);
  const [notice, setNotice] = useState('');
  const [invoices, setInvoices] = useState<SupplierInvoiceOut[]>([]);
  const [payments, setPayments] = useState<SupplierPaymentOut[]>([]);
  const [ledger, setLedger] = useState<SupplierLedgerEntry[]>([]);
  const [docs, setDocs] = useState<SupplierDocumentOut[]>([]);

  const [tabLoading, setTabLoading] = useState(false);
  const [tabError, setTabError] = useState('');
  const [invoiceSearch, setInvoiceSearch] = useState('');
  const [invoiceStatusFilter, setInvoiceStatusFilter] = useState('');
  const [invPage, setInvPage] = useState(1);
  const INV_PER_PAGE = 10;
  const [poReceipt, setPoReceipt] = useState<PurchaseOrderOut | null>(null);
  const [poReceiptLoading, setPoReceiptLoading] = useState(false);
  const [grnReceipt, setGrnReceipt] = useState<GoodsReceiptOut | null>(null);
  const [grnReceiptMeta, setGrnReceiptMeta] = useState<SupplierGRNOut | null>(null);
  const [grnReceiptLoading, setGrnReceiptLoading] = useState(false);
  const [invReceipt, setInvReceipt] = useState<SupplierInvoiceOut | null>(null);

  const loadedTabs = useRef<Set<Tab>>(new Set());

  async function openPoReceipt(poId: number) {
    setPoReceiptLoading(true);
    try {
      const r = await purchaseApi.get(poId);
      setPoReceipt(r.data);
    } catch (err) {
      setTabError(getErrorMessage(err));
    } finally {
      setPoReceiptLoading(false);
    }
  }

  async function openGrnReceipt(g: SupplierGRNOut) {
    setGrnReceiptLoading(true);
    setGrnReceiptMeta(g);
    try {
      const receipts = await purchaseApi.listReceipts(g.purchase_order_id);
      const match = receipts.data.find((r) => r.id === g.id) ?? receipts.data[0] ?? null;
      setGrnReceipt(match);
    } catch (err) {
      setTabError(getErrorMessage(err));
    } finally {
      setGrnReceiptLoading(false);
    }
  }

  useEffect(() => {
    async function loadBase() {
      setLoading(true);
      setError('');
      try {
        const [sRes, sumRes] = await Promise.all([
          supplierApi.get(supplierId),
          supplierApi.getSummary(supplierId),
        ]);
        setSupplier(sRes.data);
        setSummary(sumRes.data);
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setLoading(false);
      }
    }
    loadBase();
  }, [supplierId]);

  /** After an invoice or payment is saved: fresh totals, and the money tabs reload when opened. */
  async function refreshMoney() {
    for (const t of ['grns', 'invoices', 'payments', 'ledger', 'pos'] as Tab[]) loadedTabs.current.delete(t);
    loadTab(tab);
    try {
      setSummary((await supplierApi.getSummary(supplierId)).data);
    } catch {
      // the tables are still right; totals refresh next time
    }
  }

  async function voidPayment(p: SupplierPaymentOut) {
    if (!window.confirm(`Void this payment of ${formatCurrency(Number(p.amount))}? The invoices become unpaid by that much again.`)) return;
    try {
      await supplierPaymentApi.void(p.id);
      setNotice('Payment voided.');
      refreshMoney();
    } catch (err) {
      setTabError(getErrorMessage(err));
    }
  }

  async function cancelInvoice(inv: SupplierInvoiceOut) {
    const reason = window.prompt(`Cancel invoice ${inv.invoice_number}? Its goods receipts can then be billed on a correct invoice.\n\nReason:`);
    if (reason === null) return;
    if (!reason.trim()) {
      setTabError('A reason is needed to cancel an invoice.');
      return;
    }
    try {
      await supplierInvoiceApi.cancel(inv.id, reason.trim());
      setNotice(`Invoice ${inv.invoice_number} cancelled.`);
      refreshMoney();
    } catch (err) {
      setTabError(getErrorMessage(err));
    }
  }

  async function openDoc(docId: number) {
    try {
      await uploadApi.open(docId);
    } catch (err) {
      setTabError(getErrorMessage(err));
    }
  }

  useEffect(() => {
    if (loadedTabs.current.has(tab)) return;
    loadTab(tab);
  }, [tab]);

  async function loadTab(t: Tab) {
    setTabLoading(true);
    setTabError('');
    try {
      switch (t) {
        case 'products': {
          const r = await supplierApi.listProducts(supplierId);
          setProducts(r.data);
          break;
        }
        case 'pos': {
          const r = await purchaseApi.list({ supplier_id: supplierId, per_page: 50 });
          setPos(r.data.items);
          break;
        }
        case 'grns': {
          const r = await supplierApi.listGrns(supplierId);
          setGrns(r.data);
          break;
        }
        case 'invoices': {
          const r = await supplierInvoiceApi.list({ supplier_id: supplierId, per_page: 100 });
          setInvoices(r.data.items);
          break;
        }
        case 'payments': {
          const r = await supplierPaymentApi.list({ supplier_id: supplierId, per_page: 50 });
          setPayments(r.data.items);
          break;
        }
        case 'ledger': {
          const r = await supplierApi.getLedger(supplierId);
          setLedger(r.data);
          break;
        }
        case 'overview': {
          const r = await uploadApi.list('supplier', supplierId);
          setDocs(r.data);
          break;
        }
      }
      loadedTabs.current.add(t);
    } catch (err) {
      setTabError(getErrorMessage(err));
    } finally {
      setTabLoading(false);
    }
  }

  // ── Document upload ───────────────────────────────────────────────────────
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await uploadApi.upload(file, 'supplier', supplierId, file.name);
      loadedTabs.current.delete('overview');
      loadTab('overview');
    } catch (err) {
      setTabError(getErrorMessage(err));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function handleDeleteDoc(docId: number) {
    try {
      await uploadApi.delete(docId);
      setDocs((d) => d.filter((x) => x.id !== docId));
    } catch (err) {
      setTabError(getErrorMessage(err));
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  if (loading) return <div className="admin-page"><AdminNav /><div className="loading-text">Loading supplier…</div></div>;
  if (error) return <div className="admin-page"><AdminNav /><div className="page-error">{error}</div></div>;
  if (!supplier) return null;

  return (
    <div className="admin-page">
      <AdminNav />

      {/* Back link */}
      <button type="button" onClick={() => navigate('/admin/suppliers')} style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--color-text-muted)', fontSize: '0.88em', marginBottom: 14, padding: 0 }}>
        <IconArrowLeft size={15} /> Back to Suppliers
      </button>

      {/* Supplier header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        {/* Avatar */}
        <div style={{ width: 60, height: 60, borderRadius: 16, background: '#ede9fe', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <IconStore size={28} color="#7c3aed" />
        </div>
        {/* Name + meta */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <h2 style={{ margin: 0, fontSize: '1.45em', fontWeight: 700, letterSpacing: '-0.3px' }}>{supplier.company_name}</h2>
            <span className={`status-badge ${supplier.is_active ? 'badge-success' : 'badge-neutral'}`}>{supplier.is_active ? 'Active' : 'Inactive'}</span>
          </div>
          <div style={{ marginTop: 5, display: 'flex', gap: 18, flexWrap: 'wrap', fontSize: '0.85em', color: 'var(--color-text-muted)', alignItems: 'center' }}>
            <span style={{ fontFamily: 'monospace', background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 4, padding: '1px 6px' }}>{supplier.supplier_code}</span>
            {supplier.phone && <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.61 12a19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 3.52 1h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 8.5a16 16 0 0 0 6 6l.87-.87a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
              {supplier.phone}
            </span>}
            {supplier.gstin && <span>GSTIN: {supplier.gstin}</span>}
          </div>
        </div>
        {/* Action buttons */}
        {summary && (
          <div style={{ display: 'flex', gap: 10, flexShrink: 0 }}>
            <button className="btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: 6 }} onClick={() => setInvoiceDialog({})}><IconPlus size={14} /> Add Invoice</button>
            <button className="btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 6 }} onClick={() => setPaymentDialog({})}><IconCreditCard size={14} /> Record Payment</button>
          </div>
        )}
      </div>

      {/* Financial summary: what was ordered, received, billed, owed and paid */}
      {summary && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 12 }}>
            <AmountBadge label="PO Value" amount={summary.total_po_value} variant="neutral" icon={<IconClipboardList size={20} />} />
            <AmountBadge label="Goods Received (GRN)" amount={summary.total_received_value} variant="neutral" icon={<IconPackage size={20} />} />
            <AmountBadge label="Invoiced (As Billed)" amount={summary.total_invoiced} variant="info" icon={<IconFileText size={20} />} />
            <AmountBadge label="Total Payable" amount={summary.total_payable} variant="info" icon={<IconCreditCard size={20} />} />
            <AmountBadge label="Total Paid" amount={summary.total_paid} variant="success" icon={<IconCash size={20} />} />
            <AmountBadge label="Balance Due" amount={summary.outstanding_balance} variant={summary.outstanding_balance > 0 ? 'danger' : 'success'} icon={<IconAlert size={20} />} />
            {summary.advance_balance > 0 && <AmountBadge label="Unused Advance" amount={summary.advance_balance} variant="success" icon={<IconCheck size={20} />} />}
            <AmountBadge label="Overdue" amount={summary.overdue_amount} variant={summary.overdue_amount > 0 ? 'warning' : 'neutral'} icon={<IconAlert size={20} />} />
          </div>
          {(summary.not_invoiced_value > 0 || summary.disputed_count > 0) && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16, padding: '12px 16px', background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 10 }}>
              <div style={{ color: '#d97706', flexShrink: 0 }}><IconAlert size={20} /></div>
              <div style={{ flex: 1 }}>
                {summary.not_invoiced_value > 0 && (
                  <div style={{ fontWeight: 600, fontSize: '0.9em', color: '#92400e' }}>
                    Received but not invoiced: <span style={{ color: '#d97706' }}>{formatCurrency(summary.not_invoiced_value)}</span>
                  </div>
                )}
                <div style={{ fontSize: '0.82em', color: '#b45309', marginTop: 2 }}>
                  {summary.not_invoiced_value > 0 ? 'Goods received through GRN are pending invoicing. Link invoices to the respective GRNs.' : ''}
                  {summary.disputed_count > 0 ? ` ${summary.disputed_count} disputed invoice(s) need attention.` : ''}
                </div>
              </div>
              {summary.not_invoiced_value > 0 && (
                <button className="btn-secondary" style={{ fontSize: '0.83em', padding: '4px 12px', flexShrink: 0 }} onClick={() => setTab('grns')}>View GRNs</button>
              )}
            </div>
          )}
        </>
      )}
      {notice && <div className="notice-bar">{notice}</div>}

      {/* Tab nav */}
      <div style={{ display: 'flex', gap: 2, borderBottom: '2px solid var(--color-border)', marginBottom: 18, flexWrap: 'wrap' }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: '9px 18px',
              background: tab === t.key ? 'var(--color-primary-bg, rgba(99,102,241,0.08))' : 'none',
              border: 'none',
              borderBottom: tab === t.key ? '2px solid var(--color-primary)' : '2px solid transparent',
              borderRadius: '6px 6px 0 0',
              color: tab === t.key ? 'var(--color-primary)' : 'var(--color-text-muted)',
              fontWeight: tab === t.key ? 600 : 400,
              cursor: 'pointer',
              marginBottom: -2,
              fontSize: '0.9em',
              transition: 'color 0.15s, background 0.15s',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tabError && <div className="page-error" style={{ marginBottom: 12 }}>{tabError}</div>}
      {tabLoading && <div className="loading-text">Loading…</div>}

      {/* ── Tab: Overview ─────────────────────────────────────────────────── */}
      {tab === 'overview' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
          {/* Contact info */}
          <div className="table-card" style={{ padding: 16 }}>
            <h4 style={{ margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 8 }}>
              <IconTruck size={16} /> Contact Information
            </h4>
            <InfoRow label="Contact Person" value={supplier.contact_person} />
            <InfoRow label="Phone" value={supplier.phone} />
            <InfoRow label="Alt Phone" value={supplier.alt_phone} />
            <InfoRow label="Email" value={supplier.email} />
            <InfoRow label="GSTIN" value={supplier.gstin} />
            <InfoRow label="PAN" value={supplier.pan} />
            <InfoRow label="Payment Terms" value={supplier.payment_terms} />
            <InfoRow label="Opening Balance" value={supplier.opening_balance ? formatCurrency(Number(supplier.opening_balance)) : '₹0.00'} />
          </div>

          {/* Address */}
          <div className="table-card" style={{ padding: 16 }}>
            <h4 style={{ margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 8 }}>
              <IconClipboardList size={16} /> Address & Notes
            </h4>
            <InfoRow label="Billing Address" value={supplier.billing_address} />
            <InfoRow label="City" value={supplier.city} />
            <InfoRow label="State" value={supplier.state} />
            <InfoRow label="Pincode" value={supplier.pincode} />
            <InfoRow label="Country" value={supplier.country} />
            {supplier.notes && (
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: '0.8em', color: 'var(--color-text-muted)', marginBottom: 4 }}>Notes</div>
                <div style={{ fontSize: '0.9em', whiteSpace: 'pre-wrap' }}>{supplier.notes}</div>
              </div>
            )}
          </div>

          {/* Documents */}
          <div className="table-card" style={{ padding: 16, gridColumn: '1 / -1' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <h4 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                <IconFileText size={16} /> Documents
              </h4>
              <div>
                <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={handleUpload} accept=".pdf,.jpg,.jpeg,.png,.gif,.webp,.tiff" />
                <button className="btn-primary" style={{ fontSize: '0.85em', padding: '4px 12px' }} onClick={() => fileRef.current?.click()} disabled={uploading}>
                  {uploading ? 'Uploading…' : <><IconPlus size={13} /> Upload</>}
                </button>
              </div>
            </div>
            {docs.length === 0 ? (
              <div className="empty-row" style={{ textAlign: 'center', padding: '12px 0', color: 'var(--color-text-muted)' }}>No documents uploaded.</div>
            ) : (
              <table className="data-table">
                <thead><tr><th>Label / Filename</th><th>Type</th><th>Size</th><th>Uploaded</th><th></th></tr></thead>
                <tbody>
                  {docs.map((d) => (
                    <tr key={d.id}>
                      <td>{d.document_label ?? d.original_filename}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: '0.82em' }}>{d.mime_type}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{(d.file_size / 1024).toFixed(1)} KB</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{formatDate(d.created_at)}</td>
                      <td>
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button className="btn-icon" onClick={() => openDoc(d.id)} title="Open">
                            <IconDownload size={14} />
                          </button>
                          <button className="btn-icon btn-icon-danger" onClick={() => handleDeleteDoc(d.id)} title="Delete">
                            <IconTrash size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* ── Tab: Products ─────────────────────────────────────────────────── */}
      {tab === 'products' && (
        <div className="table-card">
          <table className="data-table">
            <thead>
              <tr>
                <th>Product</th>
                <th>Supplier Code</th>
                <th>Purchase Price</th>
                <th>Last Price</th>
                <th>Min Qty</th>
                <th>Lead Time</th>
                <th>Preferred</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => (
                <tr key={p.id}>
                  <td>
                    <div><strong>{p.product_name}</strong></div>
                    {p.product_sku && <div style={{ fontSize: '0.8em', color: 'var(--color-text-muted)' }}>{p.product_sku}</div>}
                  </td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.85em' }}>{p.supplier_product_code ?? '—'}</td>
                  <td>{p.purchase_price ? formatCurrency(Number(p.purchase_price)) : '—'}</td>
                  <td>{p.last_purchase_price ? formatCurrency(Number(p.last_purchase_price)) : '—'}</td>
                  <td>{p.min_order_qty}</td>
                  <td>{p.lead_time_days != null ? `${p.lead_time_days} days` : '—'}</td>
                  <td>{p.is_preferred ? <span className="badge-success status-badge">Yes</span> : '—'}</td>
                  <td><span className={`status-badge ${p.is_active ? 'badge-success' : 'badge-neutral'}`}>{p.is_active ? 'Active' : 'Inactive'}</span></td>
                </tr>
              ))}
              {products.length === 0 && !tabLoading && (
                <tr><td colSpan={8} className="empty-row">No products linked to this supplier.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Tab: Purchase Orders ──────────────────────────────────────────── */}
      {tab === 'pos' && (
        <div className="table-card">
          <table className="data-table">
            <thead>
              <tr>
                <th>PO Number</th>
                <th>Date</th>
                <th>Status</th>
                <th>Grand Total</th>
                <th>Expected Delivery</th>
                <th>Created By</th>
              </tr>
            </thead>
            <tbody>
              {pos.map((po) => (
                <tr key={po.id}>
                  <td>
                    <button type="button" onClick={() => openPoReceipt(po.id)}
                      style={{ fontFamily: 'monospace', fontSize: '0.88em', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-primary)', fontWeight: 600, padding: 0, textDecoration: 'underline', textDecorationStyle: 'dotted' }}>
                      {po.po_number}
                    </button>
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>{formatDate(po.purchase_date)}</td>
                  <td>
                    <span className={`status-badge ${
                      po.status === 'received' || po.status === 'closed' ? 'badge-success' :
                      po.status === 'cancelled' ? 'badge-neutral' :
                      po.status === 'ordered' ? 'badge-info' : 'badge-warning'
                    }`}>
                      {po.status.replace('_', ' ')}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right' }}>{formatCurrency(Number(po.grand_total))}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>{po.expected_delivery_date ? formatDate(po.expected_delivery_date) : '—'}</td>
                  <td>{po.created_by_name}</td>
                </tr>
              ))}
              {pos.length === 0 && !tabLoading && (
                <tr><td colSpan={6} className="empty-row">No purchase orders found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Tab: GRNs ─────────────────────────────────────────────────────── */}
      {tab === 'grns' && (
        <div className="table-card">
          <table className="data-table">
            <thead>
              <tr>
                <th>Receipt #</th>
                <th>PO</th>
                <th>Received At</th>
                <th>Items</th>
                <th style={{ textAlign: 'right' }}>Value (accepted goods)</th>
                <th>Invoice</th>
              </tr>
            </thead>
            <tbody>
              {grns.map((g) => (
                <tr key={g.id}>
                  <td>
                    <button type="button" onClick={() => openGrnReceipt(g)}
                      style={{ fontFamily: 'monospace', fontSize: '0.88em', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-primary)', fontWeight: 600, padding: 0, textDecoration: 'underline', textDecorationStyle: 'dotted' }}>
                      {g.receipt_number}
                    </button>
                  </td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.88em' }}>{g.po_number}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>{formatDate(g.received_at)}</td>
                  <td>{g.item_count}</td>
                  <td style={{ textAlign: 'right' }}>{formatCurrency(Number(g.value))}</td>
                  <td>
                    {g.invoice_number ? (
                      <span style={{ fontFamily: 'monospace', fontSize: '0.88em' }}>{g.invoice_number}</span>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'row', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.78em', fontWeight: 600, color: '#92400e', background: '#fef9c3', border: '1px solid #fde68a', borderRadius: 6, padding: '3px 8px' }}>
                          ● Not Invoiced
                        </span>
                        <button type="button" onClick={() => setInvoiceDialog({ grnId: g.id })}
                          style={{ fontSize: '0.8em', fontWeight: 600, color: '#4f46e5', background: '#eef2ff', border: '1px solid #e0e7ff', borderRadius: 6, padding: '3px 10px', cursor: 'pointer' }}>
                          + Add Invoice
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {grns.length === 0 && !tabLoading && (
                <tr><td colSpan={6} className="empty-row">No goods received from this supplier yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Tab: Invoices ─────────────────────────────────────────────────── */}
      {tab === 'invoices' && (() => {
        const filtered = invoices.filter(inv => {
          const q = invoiceSearch.toLowerCase();
          const matchQ = !q || inv.invoice_number.toLowerCase().includes(q) || (inv.po_number ?? '').toLowerCase().includes(q);
          const matchS = !invoiceStatusFilter || inv.payment_status === invoiceStatusFilter;
          return matchQ && matchS;
        });
        const totalPages = Math.max(1, Math.ceil(filtered.length / INV_PER_PAGE));
        const page = Math.min(invPage, totalPages);
        const paged = filtered.slice((page - 1) * INV_PER_PAGE, page * INV_PER_PAGE);
        return (
          <div className="table-card">
            {/* Toolbar */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 16px', borderBottom: '1px solid var(--color-border)', flexWrap: 'wrap' }}>
              <h3 style={{ margin: 0, fontSize: '1em', fontWeight: 600 }}>Invoices</h3>
              <span style={{ flex: 1 }} />
              <div style={{ position: 'relative' }}>
                <span style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)', pointerEvents: 'none' }}><IconSearch size={14} /></span>
                <input
                  type="text"
                  placeholder="Search invoice No. or PO No..."
                  value={invoiceSearch}
                  onChange={e => { setInvoiceSearch(e.target.value); setInvPage(1); }}
                  style={{ paddingLeft: 30, paddingRight: 10, height: 32, border: '1px solid var(--color-border)', borderRadius: 6, fontSize: '0.85em', background: 'var(--color-surface)', color: 'var(--color-text)', width: 240 }}
                />
              </div>
              <select value={invoiceStatusFilter} onChange={e => { setInvoiceStatusFilter(e.target.value); setInvPage(1); }}
                style={{ height: 32, border: '1px solid var(--color-border)', borderRadius: 6, fontSize: '0.85em', padding: '0 8px', background: 'var(--color-surface)', color: 'var(--color-text)' }}>
                <option value="">All Status</option>
                <option value="unpaid">Unpaid</option>
                <option value="partially_paid">Partially Paid</option>
                <option value="paid">Paid</option>
                <option value="overdue">Overdue</option>
                <option value="cancelled">Cancelled</option>
              </select>
              <button className="btn-secondary" style={{ height: 32, fontSize: '0.85em', display: 'flex', alignItems: 'center', gap: 5 }}
                onClick={() => {
                  const rows = [['Invoice #','Date','Due Date','PO/GRN','Billed','Payable','Paid','Balance','Status','Verification'].join(','),
                    ...filtered.map(i => [i.invoice_number, formatDate(i.invoice_date), i.due_date ? formatDate(i.due_date) : '', i.po_number ?? '', i.grand_total, i.payable_amount, i.amount_paid, i.outstanding, i.payment_status, i.verification_status].join(','))].join('\n');
                  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([rows], { type: 'text/csv' })); a.download = `invoices-${supplier.supplier_code}.csv`; a.click();
                }}>
                <IconDownload size={14} /> Export
              </button>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Invoice #</th>
                  <th>Date</th>
                  <th>Due Date</th>
                  <th>PO / GRN</th>
                  <th style={{ textAlign: 'right' }}>Billed Amount</th>
                  <th style={{ textAlign: 'right' }}>Paid Amount</th>
                  <th style={{ textAlign: 'right' }}>Balance</th>
                  <th>Status</th>
                  <th>Verification</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {paged.map((inv) => (
                  <tr key={inv.id}>
                    <td>
                      <button type="button" onClick={() => setInvReceipt(inv)}
                        style={{ fontFamily: 'monospace', fontSize: '0.88em', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-primary)', fontWeight: 600, padding: 0, textDecoration: 'underline', textDecorationStyle: 'dotted' }}>
                        {inv.invoice_number}
                      </button>
                      {inv.document_id && (
                        <button className="btn-icon" style={{ marginLeft: 4, verticalAlign: 'middle' }} onClick={() => openDoc(inv.document_id!)} title="View bill">
                          <IconFileText size={13} />
                        </button>
                      )}
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>{formatDate(inv.invoice_date)}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>{inv.due_date ? formatDate(inv.due_date) : '—'}</td>
                    <td style={{ fontSize: '0.82em' }}>
                      {inv.po_number ?? '—'}
                      {inv.grn_numbers.length > 0 && <div style={{ color: 'var(--color-text-muted)' }}>{inv.grn_numbers.join(', ')}</div>}
                      {inv.is_legacy && <div style={{ color: 'var(--color-text-muted)' }}>(No GRN)</div>}
                    </td>
                    <td style={{ textAlign: 'right' }}>{formatCurrency(Number(inv.grand_total))}</td>
                    <td style={{ textAlign: 'right' }}>{formatCurrency(Number(inv.amount_paid))}</td>
                    <td style={{ textAlign: 'right', fontWeight: 600, color: Number(inv.outstanding) > 0 ? '#ef4444' : undefined }}>
                      {formatCurrency(Number(inv.outstanding))}
                    </td>
                    <td>
                      <span className={`status-badge ${
                        inv.payment_status === 'paid' ? 'badge-success' :
                        inv.payment_status === 'cancelled' ? 'badge-neutral' :
                        inv.payment_status === 'partially_paid' ? 'badge-info' : 'badge-warning'
                      }`} style={{ textTransform: 'capitalize', fontSize: '0.8em' }}>
                        {inv.payment_status === 'partially_paid' ? 'Partial' : inv.payment_status.replace('_', ' ')}
                      </span>
                    </td>
                    <td>
                      <span className={`status-badge ${inv.verification_status === 'verified' ? 'badge-success' : inv.verification_status === 'disputed' ? 'badge-danger' : 'badge-neutral'}`}
                        style={{ fontSize: '0.8em', textTransform: 'capitalize' }} title={inv.difference_reason ?? undefined}>
                        {inv.verification_status}
                      </span>
                      {inv.verification_status === 'disputed' && inv.difference !== null && (
                        <div style={{ fontSize: '0.75em', color: '#ef4444' }}>diff {formatCurrency(Number(inv.difference))}</div>
                      )}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                        {inv.document_id && (
                          <button title="View attached bill" onClick={() => openDoc(inv.document_id!)}
                            style={{ width: 30, height: 30, borderRadius: 6, border: '1px solid #bfdbfe', background: '#eff6ff', color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}>
                            <IconFileText size={14} />
                          </button>
                        )}
                        {Number(inv.outstanding) > 0 && inv.payment_status !== 'cancelled' && (
                          <button title="Record payment" onClick={() => setPaymentDialog({ invoiceId: inv.id })}
                            style={{ width: 30, height: 30, borderRadius: 6, border: '1px solid #bbf7d0', background: '#f0fdf4', color: '#16a34a', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}>
                            <IconCash size={14} />
                          </button>
                        )}
                        {inv.payment_status !== 'paid' && inv.payment_status !== 'cancelled' && (
                          <button title="Edit invoice" onClick={() => setEditInvoice(inv)}
                            style={{ width: 30, height: 30, borderRadius: 6, border: '1px solid #fde68a', background: '#fffbeb', color: '#d97706', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}>
                            <IconEdit size={14} />
                          </button>
                        )}
                        {inv.payment_status !== 'cancelled' && Number(inv.amount_paid) === 0 && (
                          <button title="Cancel invoice" onClick={() => cancelInvoice(inv)}
                            style={{ width: 30, height: 30, borderRadius: 6, border: '1px solid #fecaca', background: '#fef2f2', color: '#dc2626', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}>
                            <IconTrash size={14} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {paged.length === 0 && !tabLoading && (
                  <tr><td colSpan={10} className="empty-row">{invoices.length === 0 ? 'No invoices yet. When the supplier\'s bill arrives, click "Add Invoice".' : 'No invoices match your search.'}</td></tr>
                )}
              </tbody>
            </table>
            {/* Footer */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', borderTop: '1px solid var(--color-border)', fontSize: '0.85em', color: 'var(--color-text-muted)' }}>
              <span>Showing {filtered.length === 0 ? 0 : (page - 1) * INV_PER_PAGE + 1} – {Math.min(page * INV_PER_PAGE, filtered.length)} of {filtered.length} invoice{filtered.length !== 1 ? 's' : ''}</span>
              {totalPages > 1 && (
                <div style={{ display: 'flex', gap: 4 }}>
                  <button className="btn-icon" disabled={page <= 1} onClick={() => setInvPage(p => p - 1)}>‹</button>
                  {Array.from({ length: totalPages }, (_, i) => i + 1).map(pg => (
                    <button key={pg} onClick={() => setInvPage(pg)}
                      style={{ width: 28, height: 28, borderRadius: 6, border: '1px solid var(--color-border)', background: pg === page ? 'var(--color-primary)' : 'var(--color-surface)', color: pg === page ? '#fff' : 'var(--color-text)', cursor: 'pointer', fontSize: '0.85em', fontWeight: pg === page ? 600 : 400 }}>
                      {pg}
                    </button>
                  ))}
                  <button className="btn-icon" disabled={page >= totalPages} onClick={() => setInvPage(p => p + 1)}>›</button>
                </div>
              )}
            </div>
          </div>
        );
      })()}

      {/* ── Tab: Payments ─────────────────────────────────────────────────── */}
      {tab === 'payments' && (
        <div className="table-card">
          <table className="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Type</th>
                <th>Method</th>
                <th>Amount</th>
                <th>Reference</th>
                <th>Invoices Allocated</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {payments.map((p) => (
                <tr key={p.id}>
                  <td style={{ whiteSpace: 'nowrap' }}>{formatDate(p.payment_date)}</td>
                  <td style={{ textTransform: 'capitalize' }}>
                    {p.payment_type.replace('_', ' ')}
                    {!p.is_voided && Number(p.unallocated_amount) > 0 && (
                      <div style={{ textTransform: 'none', fontSize: '0.82em' }}>
                        Unused {formatCurrency(Number(p.unallocated_amount))}{' '}
                        <button type="button" className="link-button" onClick={() => setPaymentDialog({ advance: p })}>Apply</button>
                      </div>
                    )}
                  </td>
                  <td style={{ textTransform: 'capitalize' }}>{p.payment_method.replace('_', ' ')}</td>
                  <td style={{ textAlign: 'right', fontWeight: 600 }}>{formatCurrency(Number(p.amount))}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.85em' }}>{p.reference_number ?? '—'}</td>
                  <td>
                    {p.allocations.length > 0 ? (
                      <div style={{ fontSize: '0.82em' }}>
                        {p.allocations.map((a) => (
                          <div key={a.id}>{a.invoice_number}: {formatCurrency(Number(a.allocated_amount))}</div>
                        ))}
                      </div>
                    ) : '—'}
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {p.is_voided ? (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: '0.78em', fontWeight: 600, color: '#6b7280', background: '#f3f4f6', border: '1px solid #e5e7eb', borderRadius: 20, padding: '4px 10px' }}>
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#9ca3af', flexShrink: 0 }} />
                        Voided
                      </span>
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: '0.78em', fontWeight: 600, color: '#15803d', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 20, padding: '4px 10px' }}>
                          <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#22c55e', flexShrink: 0 }} />
                          Active
                        </span>
                        <button type="button" onClick={() => voidPayment(p)}
                          style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.78em', fontWeight: 600, color: '#b91c1c', background: '#fff1f2', border: '1px solid #fecdd3', borderRadius: 20, padding: '4px 10px', cursor: 'pointer' }}>
                          ✕ Void
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {payments.length === 0 && !tabLoading && (
                <tr><td colSpan={7} className="empty-row">No payments found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Tab: Ledger ───────────────────────────────────────────────────── */}
      {tab === 'ledger' && (
        <div className="table-card">
          <table className="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Type</th>
                <th>Reference</th>
                <th>Description</th>
                <th style={{ textAlign: 'right' }}>Debit (Payable)</th>
                <th style={{ textAlign: 'right' }}>Credit (Payment)</th>
                <th style={{ textAlign: 'right' }}>Balance</th>
              </tr>
            </thead>
            <tbody>
              {ledger.map((entry, idx) => (
                <tr key={idx}>
                  <td style={{ whiteSpace: 'nowrap' }}>{formatDate(entry.date)}</td>
                  <td style={{ textTransform: 'capitalize' }}>
                    <span className={`status-badge ${entry.entry_type === 'invoice' ? 'badge-warning' : 'badge-success'}`}>
                      {entry.entry_type}
                    </span>
                  </td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.85em' }}>{entry.reference}</td>
                  <td style={{ fontSize: '0.88em' }}>{entry.description}</td>
                  <td style={{ textAlign: 'right' }}>{Number(entry.debit) > 0 ? formatCurrency(Number(entry.debit)) : '—'}</td>
                  <td style={{ textAlign: 'right' }}>{Number(entry.credit) > 0 ? formatCurrency(Number(entry.credit)) : '—'}</td>
                  <td style={{ textAlign: 'right', fontWeight: 600, color: Number(entry.balance) > 0 ? 'var(--color-danger)' : 'var(--color-success)' }}>
                    {formatCurrency(Number(entry.balance))}
                  </td>
                </tr>
              ))}
              {ledger.length === 0 && !tabLoading && (
                <tr><td colSpan={7} className="empty-row">No ledger entries found.</td></tr>
              )}
              {ledger.length > 0 && (
                <tr style={{ fontWeight: 700, background: 'var(--color-surface)' }}>
                  <td colSpan={4} style={{ textAlign: 'right', paddingRight: 16 }}>Closing Balance</td>
                  <td style={{ textAlign: 'right' }}>{formatCurrency(ledger.reduce((s, e) => s + Number(e.debit), 0))}</td>
                  <td style={{ textAlign: 'right' }}>{formatCurrency(ledger.reduce((s, e) => s + Number(e.credit), 0))}</td>
                  <td style={{ textAlign: 'right', color: Number(ledger[ledger.length - 1]?.balance) > 0 ? 'var(--color-danger)' : 'var(--color-success)' }}>
                    {formatCurrency(Number(ledger[ledger.length - 1]?.balance ?? 0))}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {invoiceDialog && (
        <SupplierInvoiceDialog
          supplier={supplier}
          preselectGrnId={invoiceDialog.grnId}
          onClose={() => setInvoiceDialog(null)}
          onSaved={(inv) => {
            setInvoiceDialog(null);
            setNotice(`Invoice ${inv.invoice_number} saved. Payable ${formatCurrency(Number(inv.payable_amount))}.`);
            setTab('invoices');
            refreshMoney();
          }}
        />
      )}
      {paymentDialog && (
        <SupplierPaymentDialog
          supplier={supplier}
          preselectInvoiceId={paymentDialog.invoiceId}
          applyAdvance={paymentDialog.advance}
          onClose={() => setPaymentDialog(null)}
          onSaved={(p) => {
            const applied = Boolean(paymentDialog.advance);
            setPaymentDialog(null);
            setNotice(applied
              ? `Advance applied. ${formatCurrency(Number(p.unallocated_amount))} of it is still unused.`
              : `${p.payment_type === 'advance' ? 'Advance' : 'Payment'} of ${formatCurrency(Number(p.amount))} recorded.`);
            refreshMoney();
          }}
        />
      )}
      {editInvoice && (
        <SupplierInvoiceEditDialog
          invoice={editInvoice}
          onClose={() => setEditInvoice(null)}
          onSaved={(inv) => {
            setEditInvoice(null);
            setNotice(`Invoice ${inv.invoice_number} updated. Payable ${formatCurrency(Number(inv.payable_amount))}.`);
            refreshMoney();
          }}
        />
      )}

      {/* Invoice Receipt modal */}
      {invReceipt && (() => {
        const paid = Number(invReceipt.amount_paid);
        const payable = Number(invReceipt.payable_amount);
        const outstanding = Number(invReceipt.outstanding);
        const pct = payable > 0 ? Math.min(100, Math.round((paid / payable) * 100)) : (paid > 0 ? 100 : 0);
        const statusColor = invReceipt.payment_status === 'paid' ? { bg: '#f0fdf4', border: '#bbf7d0', text: '#15803d', dot: '#22c55e' }
          : invReceipt.payment_status === 'partially_paid' ? { bg: '#eef2ff', border: '#e0e7ff', text: '#4f46e5', dot: '#818cf8' }
          : invReceipt.payment_status === 'cancelled' ? { bg: '#f3f4f6', border: '#e5e7eb', text: '#6b7280', dot: '#9ca3af' }
          : { bg: '#fff7ed', border: '#fed7aa', text: '#c2410c', dot: '#fb923c' };
        const statusLabel = invReceipt.payment_status === 'partially_paid' ? 'Partial' : invReceipt.payment_status === 'paid' ? 'Paid' : invReceipt.payment_status === 'cancelled' ? 'Cancelled' : 'Unpaid';
        return (
          <div className="modal-overlay" style={{ zIndex: 60 }}>
            <div className="modal-box" style={{ maxWidth: 620, width: '96%', maxHeight: '90vh', overflowY: 'auto', padding: 0, borderRadius: 16 }}>

              {/* Header bar */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '16px 22px', borderBottom: '1px solid var(--color-border)' }}>
                <div style={{ width: 42, height: 42, borderRadius: 11, background: '#eff6ff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <IconFileText size={22} color="#2563eb" />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 700, fontSize: '1.05em' }}>Supplier Invoice</div>
                  <div style={{ fontSize: '0.77em', color: 'var(--color-text-muted)' }}>View detailed information about this supplier invoice</div>
                </div>
                <button type="button" onClick={() => setInvReceipt(null)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', fontSize: '1.3em', lineHeight: 1 }}>✕</button>
              </div>

              <div style={{ padding: '0 0 20px' }}>

                {/* ── Invoice number + status ── */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 22px', background: 'linear-gradient(135deg,#eff6ff 0%,#f8faff 100%)', borderBottom: '1px solid var(--color-border)' }}>
                  <div>
                    <div style={{ fontSize: '0.7em', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 4 }}>Invoice Number</div>
                    <div style={{ fontSize: '1.25em', fontWeight: 800, fontFamily: 'monospace', color: '#1e293b', letterSpacing: '-0.5px' }}>{invReceipt.invoice_number}</div>
                  </div>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.88em', fontWeight: 700, color: statusColor.text, background: statusColor.bg, border: `1.5px solid ${statusColor.border}`, borderRadius: 20, padding: '6px 16px' }}>
                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: statusColor.dot, display: 'inline-block' }} />
                    {statusLabel}
                  </span>
                </div>

                {/* ── Info table ── */}
                <div style={{ padding: '0 22px' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 0 }}>
                    <tbody>
                      {[
                        ['Supplier', invReceipt.supplier_name, 'Invoice Date', formatDate(invReceipt.invoice_date)],
                        ['Due Date', invReceipt.due_date ? formatDate(invReceipt.due_date) : '—', 'Purchase Order', invReceipt.po_number ?? '—'],
                        ...(invReceipt.grn_numbers.length > 0 ? [['GRN(s)', invReceipt.grn_numbers.join(', '), '', '']] : []),
                        ...(invReceipt.notes ? [['Notes', invReceipt.notes, '', '']] : []),
                      ].map((row, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid var(--color-border)' }}>
                          <td style={{ padding: '10px 0 10px', width: '18%', fontSize: '0.78em', color: '#64748b', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.3px', whiteSpace: 'nowrap' }}>{row[0]}</td>
                          <td style={{ padding: '10px 20px 10px 10px', fontSize: '0.9em', fontWeight: 600, color: '#1e293b', width: '32%' }}>{row[1]}</td>
                          {row[2] ? <>
                            <td style={{ padding: '10px 0 10px', width: '18%', fontSize: '0.78em', color: '#64748b', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.3px', whiteSpace: 'nowrap', borderLeft: '1px solid var(--color-border)', paddingLeft: 20 }}>{row[2]}</td>
                            <td style={{ padding: '10px 0 10px 10px', fontSize: '0.9em', fontWeight: 600, color: '#1e293b' }}>{row[3]}</td>
                          </> : <td colSpan={2} />}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* ── Amount breakdown ── */}
                <div style={{ margin: '16px 22px 0', background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 12, overflow: 'hidden' }}>
                  <div style={{ padding: '10px 16px', background: '#f8fafc', borderBottom: '1px solid var(--color-border)', fontSize: '0.75em', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                    Amount Breakdown
                  </div>
                  {[
                    { label: 'Subtotal', value: formatCurrency(Number(invReceipt.subtotal)), bold: false },
                    ...(Number(invReceipt.tax_amount) > 0 ? [{ label: 'Tax (GST)', value: formatCurrency(Number(invReceipt.tax_amount)), bold: false }] : []),
                    ...(Number(invReceipt.other_charges) > 0 ? [{ label: 'Other Charges', value: formatCurrency(Number(invReceipt.other_charges)), bold: false }] : []),
                  ].map((r, i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 16px', borderBottom: '1px solid var(--color-border)', fontSize: '0.88em', color: '#64748b' }}>
                      <span>{r.label}</span><span>{r.value}</span>
                    </div>
                  ))}
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '13px 16px', fontWeight: 700, fontSize: '1em', color: '#1e293b', background: 'rgba(99,102,241,0.04)' }}>
                    <span>Grand Total</span>
                    <span style={{ color: '#4f46e5' }}>{formatCurrency(Number(invReceipt.grand_total))}</span>
                  </div>
                </div>

                {/* ── Payment tiles — 3 columns ── */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, margin: '14px 22px 0' }}>
                  <div style={{ padding: '12px 14px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, borderTop: '3px solid #94a3b8' }}>
                    <div style={{ fontSize: '0.72em', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 6 }}>Payable</div>
                    <div style={{ fontSize: '1.05em', fontWeight: 700, color: '#334155' }}>{formatCurrency(payable)}</div>
                  </div>
                  <div style={{ padding: '12px 14px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 10, borderTop: '3px solid #22c55e' }}>
                    <div style={{ fontSize: '0.72em', color: '#15803d', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 6 }}>Paid</div>
                    <div style={{ fontSize: '1.05em', fontWeight: 700, color: '#14532d' }}>{formatCurrency(paid)}</div>
                  </div>
                  <div style={{ padding: '12px 14px', background: outstanding > 0 ? '#fef2f2' : '#f8fafc', border: `1px solid ${outstanding > 0 ? '#fecaca' : '#e2e8f0'}`, borderRadius: 10, borderTop: `3px solid ${outstanding > 0 ? '#ef4444' : '#e2e8f0'}` }}>
                    <div style={{ fontSize: '0.72em', color: outstanding > 0 ? '#b91c1c' : '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 6 }}>Outstanding</div>
                    <div style={{ fontSize: '1.05em', fontWeight: 700, color: outstanding > 0 ? '#7f1d1d' : '#94a3b8' }}>{formatCurrency(outstanding)}</div>
                  </div>
                </div>

                {/* ── Progress bar ── */}
                <div style={{ padding: '14px 22px 0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 7, fontSize: '0.82em' }}>
                    <span style={{ color: '#64748b', fontWeight: 500 }}>Payment Progress</span>
                    <span style={{ fontWeight: 700, color: pct === 100 ? '#16a34a' : pct >= 50 ? '#4f46e5' : '#ea580c' }}>{pct}%</span>
                  </div>
                  <div style={{ height: 8, background: '#e2e8f0', borderRadius: 99, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${pct}%`, borderRadius: 99, transition: 'width 0.5s ease', background: pct === 100 ? 'linear-gradient(90deg,#22c55e,#4ade80)' : pct >= 50 ? 'linear-gradient(90deg,#6366f1,#818cf8)' : 'linear-gradient(90deg,#fb923c,#fbbf24)' }} />
                  </div>
                </div>

                {/* ── Status footer ── */}
                <div style={{ margin: '14px 22px 0', display: 'flex', alignItems: 'center', gap: 10, padding: '11px 16px', borderRadius: 10, background: invReceipt.payment_status === 'paid' ? '#f0fdf4' : invReceipt.payment_status === 'cancelled' ? '#f3f4f6' : '#fffbeb', border: `1px solid ${invReceipt.payment_status === 'paid' ? '#bbf7d0' : invReceipt.payment_status === 'cancelled' ? '#e5e7eb' : '#fde68a'}` }}>
                  <span style={{ fontSize: '1.1em' }}>{invReceipt.payment_status === 'paid' ? '✅' : invReceipt.payment_status === 'cancelled' ? '🚫' : '⏳'}</span>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.88em', color: '#1e293b' }}>
                      {invReceipt.payment_status === 'paid' ? 'Invoice fully paid' : invReceipt.payment_status === 'partially_paid' ? 'Partially paid' : invReceipt.payment_status === 'cancelled' ? 'Invoice cancelled' : 'Payment pending'}
                    </div>
                    <div style={{ fontSize: '0.76em', color: '#64748b', marginTop: 1 }}>
                      {invReceipt.payment_status === 'paid' ? 'No outstanding balance' : outstanding > 0 ? `${formatCurrency(outstanding)} still to be paid` : 'No balance due'}
                    </div>
                  </div>
                </div>

                {invReceipt.difference_reason && (
                  <div style={{ margin: '10px 22px 0', padding: '10px 14px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10, fontSize: '0.84em', color: '#991b1b' }}>
                    <strong>Dispute note:</strong> {invReceipt.difference_reason}
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })()}

      {/* GRN Receipt modal */}
      {(grnReceipt || grnReceiptLoading) && (
        <div className="modal-overlay" style={{ zIndex: 60 }}>
          <div className="modal-box" style={{ maxWidth: 580, width: '95%', maxHeight: '90vh', overflowY: 'auto', padding: 0, borderRadius: 16 }}>
            {grnReceiptLoading ? (
              <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-text-muted)' }}>Loading…</div>
            ) : grnReceipt && grnReceiptMeta && (
              <>
                {/* Header bar */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '16px 20px', borderBottom: '1px solid var(--color-border)' }}>
                  <div style={{ width: 42, height: 42, borderRadius: 11, background: '#f0fdf4', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <IconPackage size={22} color="#16a34a" />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, fontSize: '1.05em' }}>Goods Receipt Note</div>
                    <div style={{ fontSize: '0.77em', color: 'var(--color-text-muted)' }}>View details of goods received against purchase order</div>
                  </div>
                  <button type="button" onClick={() => { setGrnReceipt(null); setGrnReceiptMeta(null); }}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', fontSize: '1.3em', lineHeight: 1 }}>✕</button>
                </div>

                {/* GRN number + status */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 20px', borderBottom: '1px solid var(--color-border)', background: '#f8fdf9' }}>
                  <div>
                    <div style={{ fontSize: '0.7em', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 4 }}>GRN Number</div>
                    <div style={{ fontSize: '1.2em', fontWeight: 800, fontFamily: 'monospace', color: '#1e293b', letterSpacing: '-0.5px' }}>{grnReceipt.receipt_number}</div>
                  </div>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.85em', fontWeight: 600, color: '#15803d', background: '#f0fdf4', border: '1.5px solid #bbf7d0', borderRadius: 20, padding: '6px 14px' }}>
                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#22c55e', display: 'inline-block' }} /> Received
                  </span>
                </div>

                {/* Info cards — individual floating cards in 2-col grid */}
                <div style={{ padding: '0 20px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    {[
                      { icon: <IconClipboardList size={15} color="#4f46e5" />, iconBg: '#eef2ff', label: 'Purchase Order', value: grnReceiptMeta.po_number, mono: true },
                      { icon: <IconHistory size={15} color="#0891b2" />, iconBg: '#ecfeff', label: 'Received Date', value: formatDate(grnReceipt.received_at), mono: false },
                      { icon: <IconUsers size={15} color="#7c3aed" />, iconBg: '#f5f3ff', label: 'Received By', value: grnReceipt.received_by_name, mono: false },
                      { icon: <IconTruck size={15} color="#059669" />, iconBg: '#f0fdf4', label: 'Supplier', value: supplier.company_name, mono: false },
                    ].map((cell, i) => (
                      <div key={i} style={{ padding: '13px 15px', border: '1px solid var(--color-border)', borderRadius: 10, background: 'var(--color-surface)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 7 }}>
                          <span style={{ width: 24, height: 24, borderRadius: 6, background: cell.iconBg, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                            {cell.icon}
                          </span>
                          <span style={{ fontSize: '0.7em', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>{cell.label}</span>
                        </div>
                        <div style={{ fontWeight: 700, fontSize: '0.9em', color: '#1e293b', fontFamily: cell.mono ? 'monospace' : 'inherit' }}>{cell.value}</div>
                      </div>
                    ))}
                  </div>

                  {/* Invoice Status card */}
                  <div style={{ marginTop: 10, padding: '13px 15px', border: '1px solid var(--color-border)', borderRadius: 10, background: 'var(--color-surface)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 7 }}>
                      <span style={{ width: 24, height: 24, borderRadius: 6, background: '#fef3c7', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        <IconFileText size={15} color="#d97706" />
                      </span>
                      <span style={{ fontSize: '0.7em', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Invoice Status</span>
                    </div>
                    {grnReceiptMeta.invoice_number ? (
                      <div style={{ fontWeight: 700, fontSize: '0.9em', color: '#1e293b', fontFamily: 'monospace' }}>{grnReceiptMeta.invoice_number}</div>
                    ) : (
                      <div style={{ fontWeight: 700, fontSize: '0.9em', color: '#b45309' }}>Not Invoiced</div>
                    )}
                  </div>

                  {grnReceipt.notes && (
                    <div style={{ marginTop: 10, padding: '11px 15px', border: '1px solid #fde68a', borderRadius: 10, background: '#fffbeb', fontSize: '0.85em', color: '#92400e' }}>
                      <span style={{ fontWeight: 600 }}>Notes: </span>{grnReceipt.notes}
                    </div>
                  )}
                </div>

                {/* Items Received */}
                <div style={{ padding: '0 20px 20px' }}>
                  <div style={{ fontWeight: 700, fontSize: '0.95em', color: '#1e293b', marginBottom: 10 }}>Items Received</div>
                  <div style={{ border: '1px solid var(--color-border)', borderRadius: 10, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.84em' }}>
                      <thead>
                        <tr style={{ background: '#f8fafc' }}>
                          <th style={{ padding: '9px 12px', textAlign: 'left', fontWeight: 600, fontSize: '0.78em', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.4px', borderBottom: '1px solid var(--color-border)', width: 32 }}>#</th>
                          <th style={{ padding: '9px 12px', textAlign: 'left', fontWeight: 600, fontSize: '0.78em', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.4px', borderBottom: '1px solid var(--color-border)' }}>Product</th>
                          <th style={{ padding: '9px 12px', textAlign: 'right', fontWeight: 600, fontSize: '0.78em', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.4px', borderBottom: '1px solid var(--color-border)' }}>Qty Received</th>
                          <th style={{ padding: '9px 12px', textAlign: 'right', fontWeight: 600, fontSize: '0.78em', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.4px', borderBottom: '1px solid var(--color-border)' }}>Qty Accepted</th>
                          <th style={{ padding: '9px 12px', textAlign: 'right', fontWeight: 600, fontSize: '0.78em', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.4px', borderBottom: '1px solid var(--color-border)' }}>Qty Rejected</th>
                          <th style={{ padding: '9px 12px', textAlign: 'right', fontWeight: 600, fontSize: '0.78em', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.4px', borderBottom: '1px solid var(--color-border)' }}>Qty Damaged</th>
                          <th style={{ padding: '9px 12px', textAlign: 'left', fontWeight: 600, fontSize: '0.78em', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.4px', borderBottom: '1px solid var(--color-border)' }}>Batch #</th>
                        </tr>
                      </thead>
                      <tbody>
                        {grnReceipt.receipt_items.map((item, idx) => (
                          <tr key={item.id} style={{ borderBottom: idx < grnReceipt.receipt_items.length - 1 ? '1px solid var(--color-border)' : 'none', background: idx % 2 === 1 ? '#fafafa' : '#fff' }}>
                            <td style={{ padding: '10px 12px', color: '#94a3b8', fontWeight: 500 }}>{idx + 1}</td>
                            <td style={{ padding: '10px 12px' }}>
                              <div style={{ fontWeight: 700, color: '#1e293b', fontSize: '0.92em' }}>{item.product_name}</div>
                            </td>
                            <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 500 }}>{parseFloat(item.qty_received).toFixed(2)}</td>
                            <td style={{ padding: '10px 12px', textAlign: 'right', color: '#15803d', fontWeight: 500 }}>
                              {item.qty_accepted != null ? parseFloat(item.qty_accepted).toFixed(2) : '—'}
                            </td>
                            <td style={{ padding: '10px 12px', textAlign: 'right', color: parseFloat(item.qty_rejected) > 0 ? '#dc2626' : '#94a3b8', fontWeight: parseFloat(item.qty_rejected) > 0 ? 600 : 400 }}>
                              {parseFloat(item.qty_rejected) > 0 ? parseFloat(item.qty_rejected).toFixed(2) : '—'}
                            </td>
                            <td style={{ padding: '10px 12px', textAlign: 'right', color: parseFloat(item.qty_damaged) > 0 ? '#d97706' : '#94a3b8', fontWeight: parseFloat(item.qty_damaged) > 0 ? 600 : 400 }}>
                              {parseFloat(item.qty_damaged) > 0 ? parseFloat(item.qty_damaged).toFixed(2) : '—'}
                            </td>
                            <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontSize: '0.85em', color: item.batch_number ? '#1e293b' : '#94a3b8' }}>{item.batch_number ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {/* Total GRN Value */}
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
                    <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 10, padding: '10px 20px', textAlign: 'right', minWidth: 160 }}>
                      <div style={{ fontSize: '0.7em', color: '#2563eb', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 4 }}>Total GRN Value</div>
                      <div style={{ fontSize: '1.3em', fontWeight: 800, color: '#1e3a8a' }}>{formatCurrency(Number(grnReceiptMeta.value))}</div>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* PO Receipt modal */}
      {(poReceipt || poReceiptLoading) && (
        <div className="modal-overlay" style={{ zIndex: 60 }}>
          <div className="modal-box" style={{ maxWidth: 600, width: '95%', maxHeight: '90vh', overflowY: 'auto', padding: 0, borderRadius: 16 }}>
            {poReceiptLoading ? (
              <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-text-muted)' }}>Loading…</div>
            ) : poReceipt && (() => {
              const paid = Number(poReceipt.amount_paid);
              const payable = Number(poReceipt.payable_amount);
              const outstanding = Number(poReceipt.outstanding_amount);
              const pct = payable > 0 ? Math.min(100, Math.round((paid / payable) * 100)) : (paid > 0 ? 100 : 0);
              const statusColor = poReceipt.status === 'received' || poReceipt.status === 'closed'
                ? { bg: '#f0fdf4', border: '#bbf7d0', text: '#15803d', dot: '#22c55e' }
                : poReceipt.status === 'cancelled'
                ? { bg: '#f3f4f6', border: '#e5e7eb', text: '#6b7280', dot: '#9ca3af' }
                : poReceipt.status === 'ordered'
                ? { bg: '#eff6ff', border: '#bfdbfe', text: '#1d4ed8', dot: '#3b82f6' }
                : { bg: '#fffbeb', border: '#fde68a', text: '#b45309', dot: '#f59e0b' };
              return (
                <>
                  {/* Header bar */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '16px 20px', borderBottom: '1px solid var(--color-border)' }}>
                    <div style={{ width: 42, height: 42, borderRadius: 11, background: '#eff6ff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <IconClipboardList size={22} color="#2563eb" />
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 700, fontSize: '1.05em' }}>Purchase Order</div>
                      <div style={{ fontSize: '0.77em', color: 'var(--color-text-muted)' }}>View details of this purchase order</div>
                    </div>
                    <button type="button" onClick={() => setPoReceipt(null)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', fontSize: '1.3em', lineHeight: 1 }}>✕</button>
                  </div>

                  {/* PO number + status */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 20px', borderBottom: '1px solid var(--color-border)', background: '#f8faff' }}>
                    <div>
                      <div style={{ fontSize: '0.7em', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 4 }}>Purchase Order Number</div>
                      <div style={{ fontSize: '1.2em', fontWeight: 800, fontFamily: 'monospace', color: '#1e293b', letterSpacing: '-0.5px' }}>{poReceipt.po_number}</div>
                    </div>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.85em', fontWeight: 600, color: statusColor.text, background: statusColor.bg, border: `1.5px solid ${statusColor.border}`, borderRadius: 20, padding: '6px 14px' }}>
                      <span style={{ width: 7, height: 7, borderRadius: '50%', background: statusColor.dot, display: 'inline-block' }} />
                      {poReceipt.status.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                    </span>
                  </div>

                  {/* Info cards */}
                  <div style={{ padding: '16px 20px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                      {[
                        { icon: <IconTruck size={15} color="#059669" />, iconBg: '#f0fdf4', label: 'Supplier', value: poReceipt.supplier_name, mono: false },
                        { icon: <IconUsers size={15} color="#7c3aed" />, iconBg: '#f5f3ff', label: 'Created By', value: poReceipt.created_by_name, mono: false },
                        { icon: <IconHistory size={15} color="#0891b2" />, iconBg: '#ecfeff', label: 'Purchase Date', value: formatDate(poReceipt.purchase_date), mono: false },
                        ...(poReceipt.expected_delivery_date ? [{ icon: <IconHistory size={15} color="#d97706" />, iconBg: '#fffbeb', label: 'Expected Delivery', value: formatDate(poReceipt.expected_delivery_date), mono: false }] : []),
                        ...(poReceipt.reference_number ? [{ icon: <IconFileText size={15} color="#4f46e5" />, iconBg: '#eef2ff', label: 'Reference', value: poReceipt.reference_number, mono: true }] : []),
                      ].map((cell, i) => (
                        <div key={i} style={{ padding: '13px 15px', border: '1px solid var(--color-border)', borderRadius: 10, background: 'var(--color-surface)' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 7 }}>
                            <span style={{ width: 24, height: 24, borderRadius: 6, background: cell.iconBg, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                              {cell.icon}
                            </span>
                            <span style={{ fontSize: '0.7em', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>{cell.label}</span>
                          </div>
                          <div style={{ fontWeight: 700, fontSize: '0.9em', color: '#1e293b', fontFamily: cell.mono ? 'monospace' : 'inherit' }}>{cell.value}</div>
                        </div>
                      ))}
                    </div>
                    {poReceipt.notes && (
                      <div style={{ marginTop: 10, padding: '11px 15px', border: '1px solid #fde68a', borderRadius: 10, background: '#fffbeb', fontSize: '0.85em', color: '#92400e' }}>
                        <span style={{ fontWeight: 600 }}>Notes: </span>{poReceipt.notes}
                      </div>
                    )}
                  </div>

                  {/* Items */}
                  <div style={{ padding: '0 20px 16px' }}>
                    <div style={{ fontWeight: 700, fontSize: '0.95em', color: '#1e293b', marginBottom: 10 }}>Items</div>
                    <div style={{ border: '1px solid var(--color-border)', borderRadius: 10, overflow: 'hidden' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.84em' }}>
                        <thead>
                          <tr style={{ background: '#f8fafc' }}>
                            {['#', 'Product / SKU', 'Qty Ordered', 'Qty Received', 'Unit Price', 'Line Total'].map((h, i) => (
                              <th key={i} style={{ padding: '9px 12px', textAlign: i > 1 ? 'right' : 'left', fontWeight: 600, fontSize: '0.78em', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.4px', borderBottom: '1px solid var(--color-border)', whiteSpace: 'nowrap' }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {poReceipt.items.map((item, idx) => (
                            <tr key={item.id} style={{ borderBottom: idx < poReceipt.items.length - 1 ? '1px solid var(--color-border)' : 'none', background: idx % 2 === 1 ? '#fafafa' : '#fff' }}>
                              <td style={{ padding: '10px 12px', color: '#94a3b8', fontWeight: 500 }}>{idx + 1}</td>
                              <td style={{ padding: '10px 12px' }}>
                                <div style={{ fontWeight: 700, color: '#1e293b', fontSize: '0.92em' }}>{item.product_name}</div>
                                {item.product_sku && <div style={{ fontSize: '0.76em', color: '#94a3b8', fontFamily: 'monospace', marginTop: 1 }}>{item.product_sku}</div>}
                              </td>
                              <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 500 }}>{parseFloat(item.ordered_qty).toFixed(2)}</td>
                              <td style={{ padding: '10px 12px', textAlign: 'right', color: parseFloat(item.received_qty) > 0 ? '#15803d' : '#94a3b8', fontWeight: 500 }}>
                                {parseFloat(item.received_qty).toFixed(2)}
                              </td>
                              <td style={{ padding: '10px 12px', textAlign: 'right', color: '#475569' }}>{formatCurrency(Number(item.unit_price))}</td>
                              <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: '#1e293b' }}>{formatCurrency(Number(item.line_total))}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>

                      {/* Subtotal / Grand Total rows */}
                      <div style={{ borderTop: '1px solid var(--color-border)', background: '#f8fafc' }}>
                        {[
                          ...(Number(poReceipt.discount_amount) > 0 ? [{ label: 'Discount', value: `− ${formatCurrency(Number(poReceipt.discount_amount))}`, bold: false }] : []),
                          ...(Number(poReceipt.tax_amount) > 0 ? [{ label: 'Tax', value: formatCurrency(Number(poReceipt.tax_amount)), bold: false }] : []),
                          ...(Number(poReceipt.shipping_charges) > 0 ? [{ label: 'Shipping', value: formatCurrency(Number(poReceipt.shipping_charges)), bold: false }] : []),
                          { label: 'Subtotal', value: formatCurrency(Number(poReceipt.subtotal)), bold: false },
                          { label: 'Grand Total', value: formatCurrency(Number(poReceipt.grand_total)), bold: true },
                        ].map((row, i) => (
                          <div key={i} style={{ display: 'flex', justifyContent: 'flex-end', gap: 32, padding: `${row.bold ? 11 : 8}px 16px`, borderTop: row.bold ? '2px solid var(--color-border)' : i > 0 ? '1px solid var(--color-border)' : 'none', fontWeight: row.bold ? 700 : 400, fontSize: row.bold ? '1em' : '0.87em', color: row.bold ? '#1e293b' : '#64748b', background: row.bold ? 'rgba(99,102,241,0.04)' : 'transparent' }}>
                            <span>{row.label}</span>
                            <span style={{ minWidth: 90, textAlign: 'right', color: row.bold ? '#4f46e5' : undefined }}>{row.value}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Payment tiles */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: '0 20px 20px' }}>
                    <div style={{ padding: '14px 16px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 12 }}>
                      <div style={{ fontSize: '0.72em', color: '#15803d', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 6 }}>Amount Paid</div>
                      <div style={{ fontSize: '1.25em', fontWeight: 800, color: '#14532d', marginBottom: 10 }}>{formatCurrency(paid)}</div>
                      <div style={{ height: 5, background: '#bbf7d0', borderRadius: 99, overflow: 'hidden', marginBottom: 6 }}>
                        <div style={{ height: '100%', width: `${pct}%`, background: '#22c55e', borderRadius: 99, transition: 'width 0.4s' }} />
                      </div>
                      <div style={{ fontSize: '0.75em', color: '#15803d' }}>{pct}% of total</div>
                    </div>
                    <div style={{ padding: '14px 16px', background: outstanding > 0 ? '#fef2f2' : '#f8fafc', border: `1px solid ${outstanding > 0 ? '#fecaca' : '#e2e8f0'}`, borderRadius: 12 }}>
                      <div style={{ fontSize: '0.72em', color: outstanding > 0 ? '#b91c1c' : '#64748b', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 6 }}>Outstanding</div>
                      <div style={{ fontSize: '1.25em', fontWeight: 800, color: outstanding > 0 ? '#7f1d1d' : '#94a3b8', marginBottom: 10 }}>{formatCurrency(outstanding)}</div>
                      <div style={{ height: 5, background: outstanding > 0 ? '#fecaca' : '#e2e8f0', borderRadius: 99, overflow: 'hidden', marginBottom: 6 }}>
                        <div style={{ height: '100%', width: `${100 - pct}%`, background: outstanding > 0 ? '#ef4444' : '#cbd5e1', borderRadius: 99, transition: 'width 0.4s' }} />
                      </div>
                      <div style={{ fontSize: '0.75em', color: outstanding > 0 ? '#b91c1c' : '#64748b' }}>{100 - pct}% of total</div>
                    </div>
                  </div>
                </>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
}
