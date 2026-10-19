// Return items against a bill number. Refund is always cash; a manager approves with their PIN.
import { type FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { IconArrowLeft, IconSearch, IconX } from '../../components/common/Icons';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { getErrorMessage } from '../../services/api/httpClient';
import { createReturn, getBillsForMobile, getReturnableBill } from '../../services/api/returnApi';
import { openDrawer } from '../../services/hardware/printerService';
import type { BillForMobile, ReturnableBill, ReturnableLine } from '../../types/returns';
import { formatDateTime } from '../../utils/format';
import { formatRupees, paiseToString, toPaise } from '../../utils/money';
import { isMobile, normalizeMobile } from '../../utils/phone';

const REASONS = ['damaged', 'expired', 'wrongItem', 'changedMind', 'other'] as const;
type Reason = (typeof REASONS)[number];

interface LineState {
  qty: string;
  restock: boolean;
}

/** Parsed qty for a line, or NaN when the text isn't a valid amount for that line. */
function parseQty(line: ReturnableLine, text: string): number {
  if (text.trim() === '') return 0;
  const n = Number(text);
  if (!Number.isFinite(n) || n < 0) return NaN;
  if (!line.is_variable_weight && !Number.isInteger(n)) return NaN;
  if (Math.round(n * 1000) !== n * 1000 || n > line.qty_returnable + 1e-9) return NaN;
  return n;
}

/**
 * Refund preview in paise, the same way the server works it out: the returned share of the
 * original line (so offers/discounts are reversed fairly); the last units take exactly what's left.
 */
function refundPaise(line: ReturnableLine, qty: number): number {
  if (!(qty > 0)) return 0;
  if (Math.abs(qty - line.qty_returnable) < 1e-9) {
    return toPaise(line.remaining_line_total) - toPaise(line.remaining_discount) + toPaise(line.remaining_tax);
  }
  const ratio = qty / line.qty_sold;
  const share = (amount: string) => Math.round(toPaise(amount) * ratio);
  return share(line.line_total) - share(line.discount_amount) + share(line.tax_amount);
}

export function ReturnsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [billNumber, setBillNumber] = useState('');
  const [bill, setBill] = useState<ReturnableBill | null>(null);
  // Customer's bills when a mobile number was typed instead of a bill number.
  const [mobileBills, setMobileBills] = useState<{ mobile: string; bills: BillForMobile[] } | null>(null);
  const [lines, setLines] = useState<Record<number, LineState>>({});
  const [reason, setReason] = useState<Reason>('damaged');
  const [note, setNote] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [approving, setApproving] = useState(false);

  useKeyboardShortcuts({ Escape: () => navigate('/pos/billing') }, !approving);

  /** The box takes a bill number, or a customer mobile (lost receipt) to list their bills. */
  async function lookUp(e: FormEvent) {
    e.preventDefault();
    const text = billNumber.trim();
    if (!text) return;
    if (isMobile(text)) {
      setLoading(true);
      setError('');
      setBill(null);
      try {
        const mobile = normalizeMobile(text) as string;
        setMobileBills({ mobile, bills: await getBillsForMobile(mobile) });
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setLoading(false);
      }
      return;
    }
    await loadBill(text);
  }

  async function loadBill(number: string) {
    setLoading(true);
    setError('');
    setBill(null);
    setMobileBills(null);
    try {
      const found = await getReturnableBill(number);
      setBill(found);
      setBillNumber(found.bill_number);
      setLines(Object.fromEntries(found.lines.map((l) => [l.sale_item_id, { qty: '', restock: true }])));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  function updateLine(id: number, change: Partial<LineState>) {
    setLines((current) => ({ ...current, [id]: { ...current[id], ...change } }));
  }

  function returnAll() {
    if (!bill) return;
    setLines(Object.fromEntries(
      bill.lines.map((l) => [l.sale_item_id, { qty: l.qty_returnable > 0 ? String(l.qty_returnable) : '', restock: lines[l.sale_item_id]?.restock ?? true }]),
    ));
  }

  const parsed = bill
    ? bill.lines.map((l) => ({ line: l, qty: parseQty(l, lines[l.sale_item_id]?.qty ?? '') }))
    : [];
  const invalid = parsed.some((p) => Number.isNaN(p.qty));
  const chosen = parsed.filter((p) => p.qty > 0);
  const totalPaise = chosen.reduce((sum, p) => sum + refundPaise(p.line, p.qty), 0);
  const reasonText = `${t(`returns.reasons.${reason}`)}${note.trim() ? ` — ${note.trim()}` : ''}`;
  const canRefund = Boolean(bill?.can_return) && chosen.length > 0 && !invalid && (reason !== 'other' || note.trim() !== '');

  async function submit(approverUsername: string, approverPin: string) {
    if (!bill) return;
    const created = await createReturn({
      bill_number: bill.bill_number,
      reason: reasonText.slice(0, 255),
      approver_username: approverUsername,
      approver_pin: approverPin,
      lines: chosen.map((p) => ({
        sale_item_id: p.line.sale_item_id,
        qty: String(p.qty),
        restock: lines[p.line.sale_item_id]?.restock ?? true,
      })),
    });
    openDrawer(); // cash goes out of this drawer; don't wait for it
    navigate(`/pos/return-receipt/${created.id}?print=1`);
  }

  return (
    <div className="admin-page returns-page">
      <div className="admin-header">
        <h2>{t('returns.title')}</h2>
        <div className="admin-actions">
          <button className="btn-secondary btn-icon" onClick={() => navigate('/pos/billing')}>
            <IconArrowLeft size={15} />
            <span>{t('returns.backToBilling')}</span>
          </button>
        </div>
      </div>
      <p className="hint-text">{t('returns.hint')}</p>

      <form className="returns-lookup" onSubmit={lookUp}>
        <input
          className="field-input"
          placeholder={t('returns.billPlaceholder')}
          value={billNumber}
          onChange={(e) => setBillNumber(e.target.value)}
          autoFocus
        />
        <button className="btn-primary btn-icon" type="submit" disabled={loading || !billNumber.trim()}>
          <IconSearch size={15} />
          <span>{loading ? t('common.loading') : t('returns.find')}</span>
        </button>
      </form>

      {error && <div className="page-error">{error}</div>}

      {mobileBills && (
        <section className="returns-mobile-bills">
          {mobileBills.bills.length === 0 ? (
            <p className="hint-text">{t('returns.noBillsForMobile')}</p>
          ) : (
            <>
              <h3 className="section-title">{t('returns.billsForMobile', { mobile: mobileBills.mobile })}</h3>
              <div className="table-card">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t('returns.colBill')}</th><th>{t('returns.colDate')}</th>
                      <th className="num">{t('returns.colItems')}</th><th className="num">{t('returns.colTotal')}</th><th />
                    </tr>
                  </thead>
                  <tbody>
                    {mobileBills.bills.map((b) => (
                      <tr key={b.bill_number} className="clickable-row" onClick={() => loadBill(b.bill_number)}>
                        <td><strong>{b.bill_number}</strong></td>
                        <td>{formatDateTime(b.completed_at)}</td>
                        <td className="num">{b.items_count}</td>
                        <td className="num">{formatRupees(b.total)}</td>
                        <td className="table-actions"><button type="button" className="btn-sm">{t('returns.find')}</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      )}

      {bill && (
        <>
          <div className="returns-bill-info">
            <span><strong>{bill.bill_number}</strong></span>
            <span>{formatDateTime(bill.completed_at)}</span>
            <span>{t('returns.cashier', { name: bill.cashier_name })}</span>
            <span>{t('returns.billTotal', { amount: formatRupees(bill.total) })}</span>
            <span>{bill.payment_methods.map((m) => t(`methods.${m}`)).join(' + ')}</span>
            {bill.can_return && <span className="status-muted">{t('returns.daysLeft', { count: bill.days_left })}</span>}
          </div>
          {!bill.can_return && bill.blocked_reason && <div className="page-error">{bill.blocked_reason}</div>}

          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('returns.colItem')}</th>
                  <th className="num">{t('returns.colSold')}</th>
                  <th className="num">{t('returns.colReturned')}</th>
                  <th className="num">{t('returns.colReturnQty')}</th>
                  <th>{t('returns.colRestock')}</th>
                  <th className="num">{t('returns.colRefund')}</th>
                </tr>
              </thead>
              <tbody>
                {parsed.map(({ line, qty }) => {
                  const state = lines[line.sale_item_id];
                  const none = line.qty_returnable <= 0;
                  return (
                    <tr key={line.sale_item_id} className={none ? 'row-muted' : undefined}>
                      <td>
                        {line.product_name}
                        {line.hsn_code && <span className="status-muted"> · HSN {line.hsn_code}</span>}
                      </td>
                      <td className="num">{line.qty_sold}</td>
                      <td className="num">{line.qty_returned || '—'}</td>
                      <td className="num">
                        <input
                          className={`field-input returns-qty${Number.isNaN(qty) ? ' input-invalid' : ''}`}
                          inputMode="decimal"
                          disabled={none || !bill.can_return}
                          placeholder="0"
                          value={state?.qty ?? ''}
                          onChange={(e) => updateLine(line.sale_item_id, { qty: e.target.value })}
                          title={t('returns.maxQty', { qty: line.qty_returnable })}
                        />
                        <span className="status-muted"> / {line.qty_returnable}</span>
                      </td>
                      <td>
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            disabled={none || !bill.can_return}
                            checked={state?.restock ?? true}
                            onChange={(e) => updateLine(line.sale_item_id, { restock: e.target.checked })}
                          />
                          {state?.restock ?? true ? t('returns.backToShelf') : t('returns.damaged')}
                        </label>
                      </td>
                      <td className="num">{qty > 0 ? formatRupees(paiseToString(refundPaise(line, qty))) : '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {invalid && <div className="form-error">{t('returns.badQty')}</div>}

          {bill.can_return && (
            <div className="returns-footer">
              <div className="form-row">
                <label className="field-label">
                  {t('returns.reason')}
                  <select className="field-input" value={reason} onChange={(e) => setReason(e.target.value as Reason)}>
                    {REASONS.map((r) => <option key={r} value={r}>{t(`returns.reasons.${r}`)}</option>)}
                  </select>
                </label>
                <label className="field-label">
                  {t('returns.note')}
                  <input
                    className="field-input"
                    maxLength={150}
                    value={note}
                    placeholder={reason === 'other' ? t('returns.noteRequired') : t('returns.notePlaceholder')}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </label>
              </div>
              <div className="returns-actions">
                <button type="button" className="btn-secondary" onClick={returnAll}>{t('returns.returnAll')}</button>
                <button type="button" className="btn-primary btn-refund" disabled={!canRefund} onClick={() => setApproving(true)}>
                  {t('returns.refundCash', { amount: formatRupees(paiseToString(totalPaise)) })}
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {approving && bill && (
        <ReturnApprovalDialog
          amount={formatRupees(paiseToString(totalPaise))}
          onConfirm={submit}
          onClose={() => setApproving(false)}
        />
      )}
    </div>
  );
}

interface ApprovalProps {
  amount: string;
  /** Throws on failure (wrong PIN, stock, …); the dialog shows the message. */
  onConfirm: (username: string, pin: string) => Promise<void>;
  onClose: () => void;
}

function ReturnApprovalDialog({ amount, onConfirm, onClose }: ApprovalProps) {
  const { t } = useTranslation();
  const [username, setUsername] = useState('');
  const [pin, setPin] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useKeyboardShortcuts({ Escape: () => !busy && onClose() });

  const canSubmit = !busy && username.trim() !== '' && pin.length >= 4;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError('');
    try {
      await onConfirm(username.trim(), pin);
    } catch (err) {
      setError(getErrorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={() => !busy && onClose()}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="modal-subtitle">{t('returns.approvalSubtitle')}</span>
            <h3 className="modal-title">{t('returns.approvalTitle', { amount })}</h3>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose} disabled={busy}>
            <IconX size={18} />
          </button>
        </div>
        <p className="hint-text">{t('returns.approvalHint')}</p>
        {error && <div className="form-error">{error}</div>}
        <form onSubmit={handleSubmit} className="modal-form">
          <div className="form-row">
            <label className="field-label">
              {t('manualDiscount.managerUsername')}
              <input className="field-input" autoComplete="off" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
            </label>
            <label className="field-label">
              {t('manualDiscount.managerPin')}
              <input className="field-input" type="password" autoComplete="off" maxLength={12} value={pin} onChange={(e) => setPin(e.target.value)} />
            </label>
          </div>
          <div className="modal-buttons">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={busy}>{t('common.cancel')}</button>
            <button type="submit" className="btn-primary" disabled={!canSubmit}>
              {busy ? t('returns.refunding') : t('returns.approveRefund', { amount })}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
