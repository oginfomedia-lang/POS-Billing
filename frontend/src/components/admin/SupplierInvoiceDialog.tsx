// Admin enters a supplier's bill: tick the goods receipts (GRNs) it covers, type its amounts, attach the bill.
// What the shop owes is never more than the goods actually received; a different amount needs a reason.
import { type FormEvent, useEffect, useMemo, useState } from 'react';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { getErrorMessage } from '../../services/api/httpClient';
import { supplierApi } from '../../services/api/supplierApi';
import { type GRNPreview, supplierInvoiceApi } from '../../services/api/supplierInvoiceApi';
import type { SupplierGRNOut, SupplierInvoiceOut, SupplierOut } from '../../types/api';
import { formatDate } from '../../utils/format';
import { formatRupees, paiseToString, toPaise } from '../../utils/money';
import { IconX } from '../common/Icons';

/** Rate / round-off differences up to ₹1 are fine (same as the server). */
const TOLERANCE_PAISE = 100;

interface Props {
  supplier: SupplierOut;
  /** Open with this GRN already ticked (from the GRNs tab). */
  preselectGrnId?: number;
  onClose: () => void;
  onSaved: (invoice: SupplierInvoiceOut) => void;
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function SupplierInvoiceDialog({ supplier, preselectGrnId, onClose, onSaved }: Props) {
  const [grns, setGrns] = useState<SupplierGRNOut[] | null>(null);
  const [selected, setSelected] = useState<number[]>(preselectGrnId ? [preselectGrnId] : []);
  const [preview, setPreview] = useState<GRNPreview | null>(null);
  const [number, setNumber] = useState('');
  const [invoiceDate, setInvoiceDate] = useState(today());
  const [dueDate, setDueDate] = useState('');
  const [subtotal, setSubtotal] = useState('');
  const [tax, setTax] = useState('');
  const [other, setOther] = useState('');
  const [total, setTotal] = useState('');
  const [reason, setReason] = useState('');
  const [notes, setNotes] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useKeyboardShortcuts({ Escape: () => { if (!busy) onClose(); } });

  useEffect(() => {
    supplierApi.listGrns(supplier.id, true)
      .then((r) => setGrns(r.data))
      .catch((err) => { setGrns([]); setError(getErrorMessage(err)); });
  }, [supplier.id]);

  // What the ticked GRNs are worth, from the server (same arithmetic as the check on save).
  useEffect(() => {
    if (selected.length === 0) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    supplierInvoiceApi.previewGrns(supplier.id, selected)
      .then((r) => {
        if (cancelled) return;
        setPreview(r.data);
        setTotal((t) => t || r.data.received_value); // start from the received value
      })
      .catch((err) => { if (!cancelled) setError(getErrorMessage(err)); });
    return () => { cancelled = true; };
  }, [supplier.id, selected.join(',')]);

  // An invoice covers one PO: once a GRN is ticked, only that PO's GRNs can be added.
  const poId = grns?.find((g) => g.id === selected[0])?.purchase_order_id ?? null;
  const byPo = useMemo(() => {
    const groups = new Map<string, SupplierGRNOut[]>();
    for (const g of grns ?? []) groups.set(g.po_number, [...(groups.get(g.po_number) ?? []), g]);
    return [...groups.entries()];
  }, [grns]);

  const receivedPaise = preview ? toPaise(preview.received_value) : 0;
  const totalPaise = toPaise(total || '0');
  const otherPaise = toPaise(other || '0');
  const differencePaise = totalPaise - otherPaise - receivedPaise;
  const mismatch = preview !== null && totalPaise > 0 && Math.abs(differencePaise) > TOLERANCE_PAISE;
  const payablePaise = Math.min(totalPaise, receivedPaise + otherPaise);

  function toggle(id: number) {
    setError('');
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError('');
    if (selected.length === 0) return setError('Tick the goods receipt(s) this bill is for.');
    if (!file) return setError("Attach the supplier's bill (PDF or photo).");
    if (mismatch && !reason.trim()) return setError('Write why the bill differs from the goods received.');
    setBusy(true);
    try {
      const r = await supplierInvoiceApi.create({
        supplier_id: supplier.id,
        grn_ids: selected,
        invoice_number: number.trim(),
        invoice_date: invoiceDate,
        due_date: dueDate || null,
        subtotal: Number(subtotal || 0),
        tax_amount: Number(tax || 0),
        other_charges: Number(other || 0),
        grand_total: Number(total),
        notes: notes.trim() || null,
        difference_reason: mismatch ? reason.trim() : null,
      }, file);
      onSaved(r.data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-box modal-wide">
        <div className="modal-header">
          <div>
            <span className="modal-subtitle">{supplier.company_name}</span>
            <h3 className="modal-title">Add supplier invoice</h3>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose} disabled={busy}><IconX size={18} /></button>
        </div>

        {error && <div className="form-error">{error}</div>}

        <form className="modal-form" onSubmit={submit}>
          <div className="field-label">
            <span>1. Goods received that this bill is for</span>
            {grns === null ? (
              <div className="loading-text">Loading…</div>
            ) : grns.length === 0 ? (
              <p className="hint-text">Nothing to bill: every goods receipt from this supplier already has an invoice. Receive the goods on the purchase order first.</p>
            ) : (
              <div className="table-card import-table">
                <table className="data-table">
                  <tbody>
                    {byPo.map(([po, rows]) => rows.map((g, i) => {
                      const otherPo = poId !== null && g.purchase_order_id !== poId;
                      return (
                        <tr key={g.id} style={{ opacity: otherPo ? 0.45 : 1 }}>
                          <td>{i === 0 ? <strong>{po}</strong> : ''}</td>
                          <td>
                            <label className="checkbox-label" style={{ margin: 0 }}>
                              <input type="checkbox" checked={selected.includes(g.id)} disabled={otherPo || busy} onChange={() => toggle(g.id)} />
                              <code>{g.receipt_number}</code>
                            </label>
                          </td>
                          <td>{formatDate(g.received_at)}</td>
                          <td className="num">{formatRupees(g.value)}</td>
                        </tr>
                      );
                    }))}
                  </tbody>
                </table>
              </div>
            )}
            {preview && (
              <span className="hint-text">
                Goods received on {preview.po_number}: <strong>{formatRupees(preview.received_value)}</strong> (at PO rates, incl. GST)
              </span>
            )}
          </div>

          <div className="form-row-3">
            <label className="field-label">
              2. Invoice no.
              <input className="field-input" required maxLength={100} value={number} onChange={(e) => setNumber(e.target.value)} disabled={busy} />
            </label>
            <label className="field-label">
              Invoice date
              <input className="field-input" type="date" required value={invoiceDate} onChange={(e) => setInvoiceDate(e.target.value)} disabled={busy} />
            </label>
            <label className="field-label">
              Due date
              <input className="field-input" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} disabled={busy} />
              <span className="hint-text">Blank = from payment terms ({supplier.payment_terms.replace('_', ' ')})</span>
            </label>
          </div>
          <div className="form-row-4">
            <label className="field-label">
              Subtotal
              <input className="field-input" type="number" min="0" step="0.01" value={subtotal} onChange={(e) => setSubtotal(e.target.value)} disabled={busy} />
            </label>
            <label className="field-label">
              GST
              <input className="field-input" type="number" min="0" step="0.01" value={tax} onChange={(e) => setTax(e.target.value)} disabled={busy} />
            </label>
            <label className="field-label">
              Other charges
              <input className="field-input" type="number" min="0" step="0.01" value={other} onChange={(e) => setOther(e.target.value)} disabled={busy} />
            </label>
            <label className="field-label">
              <strong>Invoice total</strong>
              <input className="field-input" type="number" min="0.01" step="0.01" required value={total} onChange={(e) => setTotal(e.target.value)} disabled={busy} />
            </label>
          </div>

          {preview && totalPaise > 0 && (
            mismatch ? (
              <div className="page-error" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
                <div>
                  Bill {formatRupees(paiseToString(totalPaise - otherPaise))} for goods, but goods received are worth{' '}
                  {formatRupees(preview.received_value)} — difference {formatRupees(paiseToString(differencePaise))}.
                </div>
                <div>Payable: <strong>{formatRupees(paiseToString(payablePaise))}</strong> (only what was received). The invoice is marked Disputed.</div>
                <label className="field-label" style={{ width: '100%', marginTop: 6 }}>
                  Reason for the difference (required)
                  <input className="field-input" value={reason} maxLength={1000} onChange={(e) => setReason(e.target.value)} disabled={busy}
                    placeholder="e.g. Billed for 100, only 80 delivered" />
                </label>
              </div>
            ) : (
              <div className="notice-bar">Matches the goods received. Payable: <strong>{formatRupees(paiseToString(payablePaise))}</strong></div>
            )
          )}

          <label className="field-label">
            3. Supplier's bill (PDF or photo) — required
            <input className="field-input" type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} disabled={busy} />
          </label>
          <label className="field-label">
            Notes
            <input className="field-input" value={notes} onChange={(e) => setNotes(e.target.value)} disabled={busy} />
          </label>

          <div className="modal-buttons">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={busy || selected.length === 0}>
              {busy ? 'Saving…' : 'Save invoice'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
