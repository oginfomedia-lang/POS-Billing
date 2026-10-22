// The cashier's bills on their open shift, with the cash the drawer should hold (opened from their name on the POS).
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { IconArrowLeft, IconFileText } from '../../components/common/Icons';
import { ShiftCashSummary } from '../../components/pos/ShiftCashSummary';
import { useAuth } from '../../hooks/useAuth';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { getErrorMessage } from '../../services/api/httpClient';
import { getShiftBills } from '../../services/api/shiftApi';
import { useShiftStore } from '../../store/shiftStore';
import type { ShiftBill, ShiftBills } from '../../types/shift';
import { formatDateTime } from '../../utils/format';
import { formatRupees } from '../../utils/money';

const STATUS_BADGE: Record<ShiftBill['status'], string> = {
  paid: 'badge-success',
  held: 'badge-warning',
  voided: 'badge-neutral',
  open: 'badge-info',
};

export function ShiftBillsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { shift, loadActive } = useShiftStore();
  const [data, setData] = useState<ShiftBills | null>(null);
  const [error, setError] = useState('');
  const [checked, setChecked] = useState(false);

  useKeyboardShortcuts({ Escape: () => navigate('/pos/billing') });

  // The store may not have the shift yet (page reloaded): ask the server for the open one.
  useEffect(() => {
    if (shift) return;
    loadActive().finally(() => setChecked(true));
  }, [shift, loadActive]);

  useEffect(() => {
    if (!shift || shift.status !== 'open') return;
    getShiftBills(shift.id).then(setData).catch((err) => setError(getErrorMessage(err)));
  }, [shift]);

  const noShift = (checked && !shift) || shift?.status === 'closed';
  const s = data?.summary;

  return (
    <div className="admin-page shift-bills-page">
      <div className="admin-header">
        <div>
          <h2>{t('shift.billsTitle', { name: data?.cashier_name ?? user?.full_name ?? user?.username })}</h2>
          {data && (
            <p className="hint-text">
              {data.counter_code
                ? t('shift.billsSubtitleCounter', { id: data.shift.id, code: data.counter_code, opened: formatDateTime(data.shift.opened_at) })
                : t('shift.billsSubtitle', { id: data.shift.id, opened: formatDateTime(data.shift.opened_at) })}
            </p>
          )}
        </div>
        <div className="admin-actions">
          <button className="btn-secondary btn-icon" onClick={() => navigate('/pos/billing')}>
            <IconArrowLeft size={15} />
            <span>{t('shift.backToPos')}</span>
          </button>
          {!noShift && (
            <button className="btn-primary btn-icon" onClick={() => navigate('/pos/shift/close')}>
              <IconFileText size={15} />
              <span>{t('shift.goToClose')}</span>
            </button>
          )}
        </div>
      </div>

      {noShift && <div className="page-error">{t('shift.noShift')}</div>}
      {error && <div className="page-error">{error}</div>}
      {!data && !error && !noShift && <div className="loading-text">{t('common.loading')}</div>}

      {data && s && (
        <>
          <div className="shift-bills-totals">
            <div className="shift-total-tile">
              <span>{t('shift.paidBills')}</span>
              <strong>{s.paid_bills}</strong>
            </div>
            <div className="shift-total-tile">
              <span>{t('shift.salesTotal')}</span>
              <strong>{formatRupees(s.sales_total)}</strong>
            </div>
            <div className="shift-total-tile">
              <span>{t('shift.cashSales')}</span>
              <strong>{formatRupees(s.cash_sales)}</strong>
            </div>
            <div className="shift-total-tile">
              <span>{t('shift.cardSales')} + {t('shift.upiSales')}</span>
              <strong>{formatRupees(Number(s.card_sales) + Number(s.upi_sales))}</strong>
            </div>
            <div className="shift-total-tile shift-total-expected">
              <span>{t('shift.drawerTitle')}</span>
              <strong>{formatRupees(s.expected_cash)}</strong>
            </div>
          </div>

          <div className="shift-bills-body">
            <section className="table-card shift-bills-table">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t('shift.colBill')}</th>
                    <th>{t('shift.colTime')}</th>
                    <th className="num">{t('shift.colItems')}</th>
                    <th>{t('shift.colPayment')}</th>
                    <th>{t('shift.colStatus')}</th>
                    <th>{t('shift.colReturns')}</th>
                    <th className="num">{t('shift.colTotal')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.bills.length === 0 && (
                    <tr><td colSpan={7} className="empty-row">{t('shift.noBills')}</td></tr>
                  )}
                  {data.bills.map((b) => {
                    const paid = b.status === 'paid';
                    return (
                      <tr
                        key={b.id}
                        className={paid ? 'clickable-row' : undefined}
                        onClick={paid ? () => navigate(`/pos/reprint/${b.id}?from=shift`) : undefined}
                        title={paid ? t('shift.openBillHint') : undefined}
                      >
                        <td className="mono">{b.bill_number ?? `#${b.id}`}</td>
                        <td>{formatDateTime(b.completed_at ?? b.created_at)}</td>
                        <td className="num">{b.items_count}</td>
                        <td>
                          {b.payments.length === 0
                            ? '—'
                            : b.payments.map((p) => `${t(`methods.${p.method}`)} ${formatRupees(p.amount)}`).join(' + ')}
                        </td>
                        <td><span className={`status-badge ${STATUS_BADGE[b.status]}`}>{t(`shift.status.${b.status}`)}</span></td>
                        <td>{b.return_count > 0 ? t('shift.refundedOn', { amount: formatRupees(b.refunded) }) : '—'}</td>
                        <td className="num"><strong>{formatRupees(b.total)}</strong></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {data.returns.length > 0 && (
                <>
                  <h3 className="section-title">{t('shift.returnsTitle')}</h3>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>{t('shift.colReturnNo')}</th>
                        <th>{t('shift.colBill')}</th>
                        <th>{t('shift.colTime')}</th>
                        <th>{t('shift.colPayment')}</th>
                        <th className="num">{t('shift.colRefund')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.returns.map((r) => (
                        <tr key={r.id} className="clickable-row" onClick={() => navigate(`/pos/return-receipt/${r.id}`)}>
                          <td className="mono">{r.return_number ?? `#${r.id}`}</td>
                          <td className="mono">{r.bill_number ?? '—'}</td>
                          <td>{formatDateTime(r.created_at)}</td>
                          <td>{t(`methods.${r.refund_method}`)}</td>
                          <td className="num"><strong>− {formatRupees(r.refund_amount)}</strong></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </section>

            <aside className="shift-bills-side">
              <ShiftCashSummary summary={s} />
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
