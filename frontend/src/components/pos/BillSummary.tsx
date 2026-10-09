// Subtotal, discount, GST, grand total, and what the customer saves vs MRP.
import { useTranslation } from 'react-i18next';
import type { SaleOut } from '../../types/sale';
import { formatRupees, paiseToString, toPaise } from '../../utils/money';
import { IconCreditCard, IconSparkles } from '../common/Icons';

interface Props {
  sale: SaleOut | null;
  onPayClick?: () => void;
  disabled?: boolean;
}

export function BillSummary({ sale, onPayClick, disabled }: Props) {
  const { t } = useTranslation();
  const itemCount = sale?.items.reduce((n, i) => n + i.qty, 0) ?? 0;
  // Item offers + manual discounts = total discount minus the bill offer and reward points. Paise avoids float errors.
  const itemSavingsPaise = sale
    ? toPaise(sale.discount_amount) - toPaise(sale.bill_offer_discount) - toPaise(sale.reward_discount)
    : 0;
  const hasBillOffer = sale !== null && sale.bill_offer_name !== null && Number(sale.bill_offer_discount) > 0;
  const hasItems = itemCount > 0;

  return (
    <aside className="bill-summary">
      <div className="summary-header">
        <span className="summary-title">{t('pos.billSummary')}</span>
        <span className="item-count-badge">{t('pos.items', { count: itemCount })}</span>
      </div>

      <div className="summary-rows">
        <div className="summary-row">
          <span className="row-label">{t('pos.subtotal')}</span>
          <span className="row-val">{formatRupees(sale?.subtotal ?? 0)}</span>
        </div>
        {itemSavingsPaise > 0 && (
          <div className="summary-row summary-discount-row">
            <span className="row-label"><IconSparkles size={14} /> {t('pos.itemOffers')}</span>
            <span className="row-val discount-val">− {formatRupees(paiseToString(itemSavingsPaise))}</span>
          </div>
        )}
        {hasBillOffer && (
          <div className="summary-row summary-discount-row">
            <span className="row-label"><IconSparkles size={14} /> {sale.bill_offer_name}</span>
            <span className="row-val discount-val">− {formatRupees(sale.bill_offer_discount)}</span>
          </div>
        )}
        {sale && Number(sale.reward_discount) > 0 && (
          <div className="summary-row summary-discount-row">
            <span className="row-label"><IconSparkles size={14} /> {t('rewards.summaryRow', { points: sale.points_redeemed })}</span>
            <span className="row-val discount-val">− {formatRupees(sale.reward_discount)}</span>
          </div>
        )}
        <div className="summary-row">
          <span className="row-label">{t('pos.gstTax')}</span>
          <span className="row-val">{formatRupees(sale?.tax_amount ?? 0)}</span>
        </div>
      </div>

      <div className="summary-total-container">
        <div className="summary-row summary-total">
          <span className="total-label">{t('pos.grandTotal')}</span>
          <span className="total-amount">{formatRupees(sale?.total ?? 0)}</span>
        </div>
        {sale && Number(sale.total_saving) > 0 && (
          <div className="summary-row summary-you-save">
            <span className="row-label"><IconSparkles size={14} /> {t('pos.youSave')}</span>
            <span className="row-val">{formatRupees(sale.total_saving)}</span>
          </div>
        )}

        {onPayClick && (
          <button
            className="btn-pay-now"
            disabled={!hasItems || disabled}
            onClick={onPayClick}
          >
            <IconCreditCard size={20} />
            <span>{t('pos.payNowF12')}</span>
          </button>
        )}
      </div>
    </aside>
  );
}

