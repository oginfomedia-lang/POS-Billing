// Admin pays a supplier against their invoices (never against a PO). Three uses:
// - a payment against invoices: split across invoices, each up to its balance (= goods received − paid);
// - an advance before the bill arrives: may go against no invoice yet;
// - applying an earlier advance to invoices that have arrived since (applyAdvance).
import { type FormEvent, useEffect, useState } from 'react';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { getErrorMessage } from '../../services/api/httpClient';
import { supplierInvoiceApi } from '../../services/api/supplierInvoiceApi';
import { supplierPaymentApi } from '../../services/api/supplierPaymentApi';
import { uploadApi } from '../../services/api/uploadApi';
import type { SupplierInvoiceOut, SupplierOut, SupplierPaymentMethod, SupplierPaymentOut } from '../../types/api';
import { formatDate } from '../../utils/format';
import { formatRupees, paiseToString, toPaise } from '../../utils/money';
import { IconX } from '../common/Icons';

const METHODS: { value: SupplierPaymentMethod; label: string }[] = [
  { value: 'bank_transfer', label: 'Bank transfer' },
  { value: 'upi', label: 'UPI' },
  { value: 'cheque', label: 'Cheque' },
  { value: 'cash', label: 'Cash' },
  { value: 'other', label: 'Other' },
];

type Mode = 'invoices' | 'advance';

interface Props {
  supplier: SupplierOut;
  /** Open to pay this invoice (the Pay button on an invoice). */
  preselectInvoiceId?: number;
  /** Apply the unused part of this advance to invoices instead of recording a new payment. */
  applyAdvance?: SupplierPaymentOut;
  onClose: () => void;
  onSaved: (payment: SupplierPaymentOut) => void;
}

/** Fills the amount into the invoices, oldest due first, each up to its balance. */
function autoAllocate(invoices: SupplierInvoiceOut[], amountPaise: number): Record<number, string> {
  const out: Record<number, string> = {};
  let left = amountPaise;
  for (const inv of invoices) {
    const take = Math.min(toPaise(inv.outstanding), left);
    out[inv.id] = take > 0 ? paiseToString(take) : '';
    left -= Math.max(take, 0);
  }
  return out;
}

export function SupplierPaymentDialog({ supplier, preselectInvoiceId, applyAdvance, onClose, onSaved }: Props) {
  const [invoices, setInvoices] = useState<SupplierInvoiceOut[] | null>(null);
  const [mode, setMode] = useState<Mode>('invoices');
  const [amount, setAmount] = useState(applyAdvance?.unallocated_amount ?? '');
  const [alloc, setAlloc] = useState<Record<number, string>>({});
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [method, setMethod] = useState<SupplierPaymentMethod>('bank_transfer');
  const [reference, setReference] = useState('');
  const [notes, setNotes] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useKeyboardShortcuts({ Escape: () => { if (!busy) onClose(); } });

  useEffect(() => {
    supplierInvoiceApi.list({ supplier_id: supplier.id, payment_status: 'outstanding', per_page: 200 })
      .then((r) => {
        const open = r.data.items
          .filter((i) => toPaise(i.outstanding) > 0)
          .sort((a, b) => (a.due_date ?? a.invoice_date).localeCompare(b.due_date ?? b.invoice_date) || a.id - b.id);
        setInvoices(open);
        const pre = open.find((i) => i.id === preselectInvoiceId);
        if (applyAdvance) {
          setAlloc(autoAllocate(open, toPaise(applyAdvance.unallocated_amount)));
        } else if (pre) {
          setAmount(pre.outstanding);
          setAlloc({ [pre.id]: pre.outstanding });
        } else if (open.length === 0) {
          setMode('advance'); // no bill yet: only an advance makes sense
        }
      })
      .catch((err) => { setInvoices([]); setError(getErrorMessage(err)); });
  }, [supplier.id, preselectInvoiceId, applyAdvance]);

  const amountPaise = toPaise(amount || '0');
  const allocatedPaise = Object.values(alloc).reduce((s, v) => s + (v ? toPaise(v) : 0), 0);
  const balancePaise = (invoices ?? []).reduce((s, i) => s + toPaise(i.outstanding), 0);
  const overInvoice = (invoices ?? []).find((i) => alloc[i.id] && toPaise(alloc[i.id]) > toPaise(i.outstanding));
  // Exact for a payment against invoices; up to the amount for an advance (the rest is used later).
  const mustMatch = !applyAdvance && mode === 'invoices';

  function changeAmount(value: string) {
    setAmount(value);
    if (invoices && mode === 'invoices') setAlloc(autoAllocate(invoices, toPaise(value || '0')));
  }

  function changeMode(next: Mode) {
    setMode(next);
    setAlloc(next === 'invoices' && invoices ? autoAllocate(invoices, amountPaise) : {});
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError('');
    if (amountPaise <= 0) return setError('Enter the amount paid.');
    if (overInvoice) return setError(`Invoice ${overInvoice.invoice_number}: only ${formatRupees(overInvoice.outstanding)} is left to pay.`);
    if (mustMatch && allocatedPaise !== amountPaise) {
      return setError(`The amounts against the invoices (${formatRupees(paiseToString(allocatedPaise))}) must add up to the payment (${formatRupees(paiseToString(amountPaise))}). If part of it is paid ahead of a bill, record it as an advance.`);
    }
    if (!mustMatch && allocatedPaise > amountPaise) {
      return setError(`The amounts against the invoices (${formatRupees(paiseToString(allocatedPaise))}) are more than ${formatRupees(paiseToString(amountPaise))}.`);
    }
    if (applyAdvance && allocatedPaise <= 0) return setError('Enter how much of the advance goes against which invoice.');
    const allocations = Object.entries(alloc)
      .filter(([, v]) => v && toPaise(v) > 0)
      .map(([id, v]) => ({ invoice_id: Number(id), allocated_amount: Number(v) }));
    setBusy(true);
    try {
      if (applyAdvance) {
        onSaved((await supplierPaymentApi.applyAdvance(applyAdvance.id, allocations)).data);
        return;
      }
      const r = await supplierPaymentApi.create({
        supplier_id: supplier.id,
        payment_date: date,
        amount: Number(paiseToString(amountPaise)),
        payment_type: mode === 'advance' ? 'advance' : 'payment',
        payment_method: method,
        reference_number: reference.trim() || null,
        notes: notes.trim() || null,
        allocations,
      });
      if (file) {
        try {
          await uploadApi.upload(file, 'supplier_payment', r.data.id, 'Payment receipt');
        } catch (err) {
          // The payment is saved; only the receipt file failed.
          window.alert(`Payment saved, but the receipt file wasn't uploaded: ${getErrorMessage(err)}`);
        }
      }
      onSaved(r.data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const title = applyAdvance ? 'Apply advance to invoices' : mode === 'advance' ? 'Record advance' : 'Record payment';

  return (
    <div className="modal-overlay" onClick={() => !busy && onClose()}>
      <div className="modal-box modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="modal-subtitle">{supplier.company_name}</span>
            <h3 className="modal-title">{title}</h3>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose} disabled={busy}><IconX size={18} /></button>
        </div>

        {error && <div className="form-error">{error}</div>}

        {invoices === null ? (
          <div className="loading-text">Loading…</div>
        ) : applyAdvance && invoices.length === 0 ? (
          <div className="modal-form">
            <p className="hint-text">No unpaid invoices yet. Add the supplier's invoice first, then apply the advance to it.</p>
            <div className="modal-buttons"><button type="button" className="btn-primary" onClick={onClose}>Close</button></div>
          </div>
        ) : (
          <form className="modal-form" onSubmit={submit}>
            {applyAdvance ? (
              <div className="notice-bar notice-info">
                Advance of {formatRupees(applyAdvance.amount)} paid on {formatDate(applyAdvance.payment_date)} —{' '}
                <strong>{formatRupees(applyAdvance.unallocated_amount)}</strong> not used yet.
              </div>
            ) : (
              <>
                <div className="pay-tabs" role="tablist">
                  <button type="button" role="tab" aria-selected={mode === 'invoices'} disabled={invoices.length === 0 || busy}
                    className={`pay-tab${mode === 'invoices' ? ' active' : ''}`} onClick={() => changeMode('invoices')}>
                    Against invoices
                  </button>
                  <button type="button" role="tab" aria-selected={mode === 'advance'} disabled={busy}
                    className={`pay-tab${mode === 'advance' ? ' active' : ''}`} onClick={() => changeMode('advance')}>
                    Advance (before the bill)
                  </button>
                </div>
                {mode === 'advance' && (
                  <p className="hint-text">
                    Money paid before the supplier's bill (e.g. before delivery). When the bill arrives, use "Apply" on this
                    advance in the Payments tab.{invoices.length > 0 && ' You can also put part of it against an unpaid invoice now.'}
                  </p>
                )}
                <div className="form-row-3">
                  <label className="field-label">
                    Amount paid
                    <input className="field-input pay-amount" type="number" min="0.01" step="0.01" required autoFocus value={amount}
                      onChange={(e) => changeAmount(e.target.value)} disabled={busy} />
                    {invoices.length > 0 && <span className="hint-text">Invoices balance: {formatRupees(paiseToString(balancePaise))}</span>}
                  </label>
                  <label className="field-label">
                    Date
                    <input className="field-input" type="date" required value={date} onChange={(e) => setDate(e.target.value)} disabled={busy} />
                  </label>
                  <label className="field-label">
                    Method
                    <select className="field-input" value={method} onChange={(e) => setMethod(e.target.value as SupplierPaymentMethod)} disabled={busy}>
                      {METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                    </select>
                  </label>
                </div>
                <div className="form-row">
                  <label className="field-label">
                    Reference (UTR / cheque no.)
                    <input className="field-input" maxLength={100} value={reference} onChange={(e) => setReference(e.target.value)} disabled={busy} />
                  </label>
                  <label className="field-label">
                    Receipt file (optional)
                    <input className="field-input" type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} disabled={busy} />
                  </label>
                </div>
              </>
            )}

            {invoices.length > 0 && (
              <div className="field-label">
                <span>{applyAdvance ? 'Apply to these invoices' : mode === 'advance' ? 'Against invoices now (optional)' : 'Pay against these invoices'}</span>
                <div className="table-card import-table">
                  <table className="data-table">
                    <thead>
                      <tr><th>Invoice</th><th>Due</th><th className="num">Payable</th><th className="num">Paid</th><th className="num">Balance</th><th className="num">Pay now</th></tr>
                    </thead>
                    <tbody>
                      {invoices.map((inv) => (
                        <tr key={inv.id}>
                          <td>
                            <code>{inv.invoice_number}</code>
                            {inv.verification_status === 'disputed' && <span className="barcode-badge badge-error" style={{ marginLeft: 6 }}>Disputed</span>}
                          </td>
                          <td>{inv.due_date ? formatDate(inv.due_date) : '—'}</td>
                          <td className="num">{formatRupees(inv.payable_amount)}</td>
                          <td className="num">{formatRupees(inv.amount_paid)}</td>
                          <td className="num"><strong>{formatRupees(inv.outstanding)}</strong></td>
                          <td className="num">
                            <input className="field-input" style={{ width: 110, textAlign: 'right' }} type="number" min="0" step="0.01"
                              max={inv.outstanding} value={alloc[inv.id] ?? ''} disabled={busy}
                              onChange={(e) => setAlloc((a) => ({ ...a, [inv.id]: e.target.value }))} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <span className={!mustMatch || allocatedPaise === amountPaise ? 'hint-text' : 'import-error'}>
                  Against invoices: {formatRupees(paiseToString(allocatedPaise))} of {formatRupees(paiseToString(amountPaise))}
                  {!mustMatch && amountPaise > allocatedPaise && ` — ${formatRupees(paiseToString(amountPaise - allocatedPaise))} stays as advance`}
                </span>
              </div>
            )}

            {!applyAdvance && (
              <label className="field-label">
                Notes
                <input className="field-input" value={notes} onChange={(e) => setNotes(e.target.value)} disabled={busy} />
              </label>
            )}

            <div className="modal-buttons">
              <button type="button" className="btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
              <button type="submit" className="btn-primary" disabled={busy || amountPaise <= 0}>
                {busy ? 'Saving…' : applyAdvance ? `Apply ${formatRupees(paiseToString(allocatedPaise))}` : `Pay ${formatRupees(paiseToString(amountPaise))}`}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
