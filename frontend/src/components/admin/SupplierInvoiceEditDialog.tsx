// Correct a supplier invoice: number, dates, amounts, notes, or a better scan of the bill.
// The payable amount is worked out again (never more than the goods received); paid invoices can't change.
import { type FormEvent, useState } from 'react';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { getErrorMessage } from '../../services/api/httpClient';
import { supplierInvoiceApi } from '../../services/api/supplierInvoiceApi';
import { uploadApi } from '../../services/api/uploadApi';
import type { SupplierInvoiceOut } from '../../types/api';
import { formatRupees, paiseToString, toPaise } from '../../utils/money';
import { IconX } from '../common/Icons';

/** Rate / round-off differences up to ₹1 are fine (same as the server). */
const TOLERANCE_PAISE = 100;

interface Props {
  invoice: SupplierInvoiceOut;
  onClose: () => void;
  onSaved: (invoice: SupplierInvoiceOut) => void;
}

export function SupplierInvoiceEditDialog({ invoice, onClose, onSaved }: Props) {
  const [number, setNumber] = useState(invoice.invoice_number);
  const [invoiceDate, setInvoiceDate] = useState(invoice.invoice_date);
  const [dueDate, setDueDate] = useState(invoice.due_date ?? '');
  const [subtotal, setSubtotal] = useState(invoice.subtotal);
  const [tax, setTax] = useState(invoice.tax_amount);
  const [other, setOther] = useState(invoice.other_charges);
  const [total, setTotal] = useState(invoice.grand_total);
  const [reason, setReason] = useState(invoice.difference_reason ?? '');
  const [notes, setNotes] = useState(invoice.notes ?? '');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useKeyboardShortcuts({ Escape: () => { if (!busy) onClose(); } });

  const received = invoice.received_value; // null = old invoice without GRNs: payable is its total
  const receivedPaise = received !== null ? toPaise(received) : 0;
  const totalPaise = toPaise(total || '0');
  const otherPaise = toPaise(other || '0');
  const differencePaise = totalPaise - otherPaise - receivedPaise;
  const mismatch = received !== null && Math.abs(differencePaise) > TOLERANCE_PAISE;
  const payablePaise = received !== null ? Math.min(totalPaise, receivedPaise + otherPaise) : totalPaise;
  const paidPaise = toPaise(invoice.amount_paid);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError('');
    if (mismatch && !reason.trim()) return setError('Write why the bill differs from the goods received.');
    if (payablePaise < paidPaise) return setError(`${formatRupees(invoice.amount_paid)} is already paid; the payable amount can't go below that.`);
    setBusy(true);
    try {
      let saved = (await supplierInvoiceApi.update(invoice.id, {
        invoice_number: number.trim(),
        invoice_date: invoiceDate,
        due_date: dueDate || null,
        subtotal: Number(subtotal || 0),
        tax_amount: Number(tax || 0),
        other_charges: Number(other || 0),
        grand_total: Number(total),
        difference_reason: mismatch ? reason.trim() : null,
        notes: notes.trim() || null,
      })).data;
      if (file) {
        await uploadApi.upload(file, 'supplier_invoice', invoice.id, 'Supplier invoice (replaced)');
        saved = (await supplierInvoiceApi.get(invoice.id)).data;
      }
      onSaved(saved);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={() => !busy && onClose()}>
      <div className="modal-box modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="modal-subtitle">{invoice.supplier_name} · {invoice.po_number ?? 'no PO'}</span>
            <h3 className="modal-title">Edit invoice {invoice.invoice_number}</h3>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose} disabled={busy}><IconX size={18} /></button>
        </div>

        {error && <div className="form-error">{error}</div>}

        <form className="modal-form" onSubmit={submit}>
          <p className="hint-text">
            {received !== null
              ? <>Goods received ({invoice.grn_numbers.join(', ')}): <strong>{formatRupees(received)}</strong>.</>
              : <>Old invoice without goods receipts: the payable amount is its total.</>}
            {paidPaise > 0 && <> Already paid: <strong>{formatRupees(invoice.amount_paid)}</strong>.</>}
          </p>
          <div className="form-row-3">
            <label className="field-label">
              Invoice no.
              <input className="field-input" required maxLength={100} value={number} onChange={(e) => setNumber(e.target.value)} disabled={busy} />
            </label>
            <label className="field-label">
              Invoice date
              <input className="field-input" type="date" required value={invoiceDate} onChange={(e) => setInvoiceDate(e.target.value)} disabled={busy} />
            </label>
            <label className="field-label">
              Due date
              <input className="field-input" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} disabled={busy} />
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

          {mismatch ? (
            <div className="page-error" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
              <div>Difference from the goods received: {formatRupees(paiseToString(differencePaise))}. Payable: <strong>{formatRupees(paiseToString(payablePaise))}</strong> (Disputed).</div>
              <label className="field-label" style={{ width: '100%', marginTop: 6 }}>
                Reason for the difference (required)
                <input className="field-input" value={reason} maxLength={1000} onChange={(e) => setReason(e.target.value)} disabled={busy} />
              </label>
            </div>
          ) : (
            <div className="notice-bar">Payable: <strong>{formatRupees(paiseToString(payablePaise))}</strong></div>
          )}

          <label className="field-label">
            Replace the bill's file (optional)
            <input className="field-input" type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} disabled={busy} />
          </label>
          <label className="field-label">
            Notes
            <input className="field-input" value={notes} onChange={(e) => setNotes(e.target.value)} disabled={busy} />
          </label>

          <div className="modal-buttons">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
