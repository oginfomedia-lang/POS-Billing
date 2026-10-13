// Supplier detail page — tabbed view: Overview, Products, POs, GRNs, Invoices, Payments, Ledger.
// The admin enters the supplier's bills (Invoices) and pays against them (Payments); what is owed is
// never more than the goods actually received (GRNs).
import { useEffect, useRef, useState } from 'react';
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

function AmountBadge({ label, amount, variant }: { label: string; amount: string | number; variant?: 'danger' | 'success' | 'neutral' }) {
  const color = variant === 'danger' ? 'var(--color-danger)' : variant === 'success' ? 'var(--color-success)' : 'var(--color-text)';
  return (
    <div style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 8, padding: '10px 16px', textAlign: 'center', minWidth: 140 }}>
      <div style={{ fontSize: '1.1em', fontWeight: 700, color }}>{formatCurrency(Number(amount))}</div>
      <div style={{ fontSize: '0.8em', color: 'var(--color-text-muted)', marginTop: 2 }}>{label}</div>
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

  const loadedTabs = useRef<Set<Tab>>(new Set());

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

      {/* Back + header */}
      <div className="admin-header" style={{ marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button className="btn-icon" onClick={() => navigate('/admin/suppliers')} title="Back to Suppliers">
            <IconArrowLeft size={18} />
          </button>
          <IconTruck size={22} />
          <h2 style={{ margin: 0 }}>{supplier.company_name}</h2>
          <span style={{ fontFamily: 'monospace', fontSize: '0.8em', color: 'var(--color-text-muted)', padding: '2px 8px', background: 'var(--color-surface)', borderRadius: 4, border: '1px solid var(--color-border)' }}>
            {supplier.supplier_code}
          </span>
          <span className={`status-badge ${supplier.is_active ? 'badge-success' : 'badge-neutral'}`}>
            {supplier.is_active ? 'Active' : 'Inactive'}
          </span>
        </div>
      </div>

      {/* Financial summary: what was ordered, received, billed, owed and paid */}
      {summary && (
        <>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 8 }}>
            <AmountBadge label="PO value" amount={summary.total_po_value} />
            <AmountBadge label="Goods received (GRN)" amount={summary.total_received_value} />
            <AmountBadge label="Invoiced (as billed)" amount={summary.total_invoiced} />
            <AmountBadge label="Payable" amount={summary.total_payable} />
            <AmountBadge label="Paid" amount={summary.total_paid} variant="success" />
            <AmountBadge label="Balance to pay" amount={summary.outstanding_balance} variant={summary.outstanding_balance > 0 ? 'danger' : 'neutral'} />
            {summary.advance_balance > 0 && <AmountBadge label="Unused advance" amount={summary.advance_balance} variant="success" />}
            <AmountBadge label="Overdue" amount={summary.overdue_amount} variant={summary.overdue_amount > 0 ? 'danger' : 'neutral'} />
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 16 }}>
            {summary.not_invoiced_value > 0 && (
              <span className="hint-text">
                Received but not invoiced yet: <strong>{formatCurrency(summary.not_invoiced_value)}</strong>{' '}
                <button type="button" className="link-button" onClick={() => setInvoiceDialog({})}>Add invoice</button>
              </span>
            )}
            {summary.disputed_count > 0 && (
              <span className="barcode-badge badge-error">{summary.disputed_count} disputed invoice(s)</span>
            )}
            <span style={{ flex: 1 }} />
            <button className="btn-secondary" onClick={() => setInvoiceDialog({})}><IconPlus size={13} /> Add invoice</button>
            <button className="btn-primary" onClick={() => setPaymentDialog({})}>Record payment / advance</button>
          </div>
        </>
      )}
      {notice && <div className="notice-bar">{notice}</div>}

      {/* Tab nav */}
      <div style={{ display: 'flex', gap: 4, borderBottom: '2px solid var(--color-border)', marginBottom: 16, flexWrap: 'wrap' }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: '8px 16px',
              background: 'none',
              border: 'none',
              borderBottom: tab === t.key ? '2px solid var(--color-primary)' : '2px solid transparent',
              color: tab === t.key ? 'var(--color-primary)' : 'var(--color-text-muted)',
              fontWeight: tab === t.key ? 600 : 400,
              cursor: 'pointer',
              marginBottom: -2,
              fontSize: '0.92em',
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
                  <td><span style={{ fontFamily: 'monospace', fontSize: '0.88em' }}>{po.po_number}</span></td>
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
                  <td style={{ fontFamily: 'monospace', fontSize: '0.88em' }}>{g.receipt_number}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.88em' }}>{g.po_number}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>{formatDate(g.received_at)}</td>
                  <td>{g.item_count}</td>
                  <td style={{ textAlign: 'right' }}>{formatCurrency(Number(g.value))}</td>
                  <td>
                    {g.invoice_number ? (
                      <span style={{ fontFamily: 'monospace', fontSize: '0.88em' }}>{g.invoice_number}</span>
                    ) : (
                      <span>
                        <span className="status-badge badge-warning">Not invoiced</span>{' '}
                        <button type="button" className="link-button" onClick={() => setInvoiceDialog({ grnId: g.id })}>Add invoice</button>
                      </span>
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
      {tab === 'invoices' && (
        <div className="table-card">
          <table className="data-table">
            <thead>
              <tr>
                <th>Invoice #</th>
                <th>Date</th>
                <th>Due</th>
                <th>PO / GRNs</th>
                <th style={{ textAlign: 'right' }}>Billed</th>
                <th style={{ textAlign: 'right' }}>Payable</th>
                <th style={{ textAlign: 'right' }}>Paid</th>
                <th style={{ textAlign: 'right' }}>Balance</th>
                <th>Status</th>
                <th>Check</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv) => (
                <tr key={inv.id}>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.88em' }}>{inv.invoice_number}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>{formatDate(inv.invoice_date)}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>{inv.due_date ? formatDate(inv.due_date) : '—'}</td>
                  <td style={{ fontSize: '0.82em' }}>
                    {inv.po_number ?? '—'}
                    {inv.grn_numbers.length > 0 && <div style={{ color: 'var(--muted)' }}>{inv.grn_numbers.join(', ')}</div>}
                    {inv.is_legacy && <div style={{ color: 'var(--muted)' }}>old (no GRN)</div>}
                  </td>
                  <td style={{ textAlign: 'right' }}>{formatCurrency(Number(inv.grand_total))}</td>
                  <td style={{ textAlign: 'right' }} title={inv.received_value !== null ? `Goods received: ${formatCurrency(Number(inv.received_value))}` : undefined}>
                    {formatCurrency(Number(inv.payable_amount))}
                  </td>
                  <td style={{ textAlign: 'right' }}>{formatCurrency(Number(inv.amount_paid))}</td>
                  <td style={{ textAlign: 'right', fontWeight: 600, color: Number(inv.outstanding) > 0 ? 'var(--danger-text)' : undefined }}>
                    {formatCurrency(Number(inv.outstanding))}
                  </td>
                  <td>
                    <span className={`status-badge ${
                      inv.payment_status === 'paid' ? 'badge-success' :
                      inv.payment_status === 'cancelled' ? 'badge-neutral' :
                      inv.payment_status === 'partially_paid' ? 'badge-info' : 'badge-warning'
                    }`}>
                      {inv.payment_status.replace('_', ' ')}
                    </span>
                  </td>
                  <td>
                    <span
                      className={`status-badge ${inv.verification_status === 'verified' ? 'badge-success' : inv.verification_status === 'disputed' ? 'badge-danger' : 'badge-neutral'}`}
                      title={inv.difference_reason ?? undefined}
                    >
                      {inv.verification_status}
                    </span>
                    {inv.verification_status === 'disputed' && inv.difference !== null && (
                      <div style={{ fontSize: '0.78em', color: 'var(--danger-text)' }}>diff {formatCurrency(Number(inv.difference))}</div>
                    )}
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {inv.document_id && (
                      <button className="btn-icon" onClick={() => openDoc(inv.document_id!)} title="Open the bill">
                        <IconFileText size={14} />
                      </button>
                    )}
                    {Number(inv.outstanding) > 0 && inv.payment_status !== 'cancelled' && (
                      <button className="btn-primary btn-compact" onClick={() => setPaymentDialog({ invoiceId: inv.id })}>Pay</button>
                    )}
                    {inv.payment_status !== 'paid' && inv.payment_status !== 'cancelled' && (
                      <button type="button" className="link-button" style={{ marginLeft: 6 }} onClick={() => setEditInvoice(inv)}>Edit</button>
                    )}
                    {inv.payment_status !== 'cancelled' && Number(inv.amount_paid) === 0 && (
                      <button type="button" className="link-button" style={{ marginLeft: 6 }} onClick={() => cancelInvoice(inv)}>Cancel</button>
                    )}
                  </td>
                </tr>
              ))}
              {invoices.length === 0 && !tabLoading && (
                <tr><td colSpan={11} className="empty-row">No invoices yet. When the supplier's bill arrives, click "Add invoice".</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

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
                    {p.is_voided
                      ? <span className="status-badge badge-neutral">Voided</span>
                      : (
                        <>
                          <span className="status-badge badge-success">Active</span>{' '}
                          <button type="button" className="link-button" onClick={() => voidPayment(p)}>Void</button>
                        </>
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
    </div>
  );
}
