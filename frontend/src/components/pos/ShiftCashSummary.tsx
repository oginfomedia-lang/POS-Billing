// What the drawer should hold for a shift, from the server's figures (the same ones used to close it):
// opening float + cash sales − cash refunds. Card and UPI are shown apart; they never go in the drawer.
import { useTranslation } from 'react-i18next';
import type { ShiftSummary } from '../../types/shift';
import { formatRupees } from '../../utils/money';

export function ShiftCashSummary({ summary }: { summary: ShiftSummary }) {
  const { t } = useTranslation();
  const digital = Number(summary.card_sales) + Number(summary.upi_sales);

  return (
    <div className="shift-cash">
      <div className="shift-summary">
        <div className="shift-summary-row">
          <span>{t('shift.openingFloat')}</span>
          <strong>{formatRupees(summary.opening_float)}</strong>
        </div>
        <div className="shift-summary-row">
          <span>+ {t('shift.cashSales')}</span>
          <strong>{formatRupees(summary.cash_sales)}</strong>
        </div>
        <div className="shift-summary-row">
          <span>− {t('shift.cashRefunds')}</span>
          <strong>{formatRupees(summary.cash_refunds)}</strong>
        </div>
        <div className="shift-summary-row shift-expected-row">
          <span>
            = {t('shift.drawerTitle')}
            <small>{t('shift.drawerFormula')}</small>
          </span>
          <strong>{formatRupees(summary.expected_cash)}</strong>
        </div>
      </div>

      {digital > 0 && (
        <div className="shift-summary shift-digital">
          <div className="shift-summary-row">
            <span>{t('shift.cardSales')}</span>
            <strong>{formatRupees(summary.card_sales)}</strong>
          </div>
          <div className="shift-summary-row">
            <span>{t('shift.upiSales')}</span>
            <strong>{formatRupees(summary.upi_sales)}</strong>
          </div>
          <p className="hint-text">{t('shift.digitalNote')}</p>
        </div>
      )}
      {Number(summary.other_refunds) > 0 && (
        <p className="hint-text">{t('shift.otherRefunds')}: {formatRupees(summary.other_refunds)}</p>
      )}
      {summary.held_bills > 0 && <p className="hint-text">{t('shift.heldNote', { count: summary.held_bills })}</p>}
      {summary.voided_bills > 0 && <p className="hint-text">{t('shift.voidedNote', { count: summary.voided_bills })}</p>}
    </div>
  );
}
