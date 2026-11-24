// The printed bill (80 mm receipt), shared by the bill screen and offline bills.
import { Fragment } from 'react';
import { useTranslation } from 'react-i18next';
import type { ReceiptOut } from '../../types/sale';
import { VENDOR_CREDIT } from '../../utils/brand';
import { formatDateTime } from '../../utils/format';
import { formatRupees, paiseToString } from '../../utils/money';
import { receiptWithGst } from './receiptGst';

export function ReceiptView({ receipt }: { receipt: ReceiptOut }) {
  const { t, i18n } = useTranslation();
  // Prices are saved before GST; every rate, amount and saving is printed with GST, so subtotal − savings = total.
  const gst = receiptWithGst(receipt);
  const money = (paise: number) => paiseToString(paise);

  return (
    <article className="receipt">
      <header className="receipt-center">
        <strong className="receipt-store">{receipt.store_name}</strong>
        {receipt.receipt_header && <div className="receipt-header-line">{receipt.receipt_header}</div>}
        {receipt.store_phone && <div>{t('receipt.phone', { phone: receipt.store_phone })}</div>}
        {receipt.store_gstin && <div>{t('receipt.gstin', { gstin: receipt.store_gstin })}</div>}
        {receipt.fssai_number && <div>{t('receipt.fssai', { number: receipt.fssai_number })}</div>}
        {receipt.store_address && <div>{receipt.store_address}</div>}
      </header>

      <hr />
      <div className="receipt-row"><span>{t('receipt.billNo')}</span><span>{receipt.bill_number}</span></div>
      <div className="receipt-row"><span>{t('receipt.date')}</span><span>{formatDateTime(receipt.completed_at)}</span></div>
      <div className="receipt-row">
        <span>{receipt.counter_code ? t('receipt.counter', { code: receipt.counter_code }) : ''}</span><span>{receipt.cashier_name}</span>
      </div>
      {receipt.customer_mobile && (
        <div className="receipt-row"><span>{t('receipt.customer')}</span><span>{receipt.customer_mobile}</span></div>
      )}
      <hr />

      <table className="receipt-items">
        <thead>
          <tr><th>{t('receipt.item')}</th><th className="num">{t('receipt.qty')}</th><th className="num">{t('receipt.rate')}</th><th className="num">{t('receipt.amount')}</th></tr>
        </thead>
        <tbody>
          {receipt.items.map((i, n) => (
            <Fragment key={i.id}>
              <tr>
                <td>{n + 1}. {i.product_name}</td>
                <td className="num">{i.is_variable_weight ? `${i.qty} ${i.uom}` : i.qty}</td>
                <td className="num">{money(gst.lines[n].rate)}</td>
                <td className="num">{money(gst.lines[n].amount)}</td>
              </tr>
              {(i.hsn_code || i.mrp) && (
                <tr className="receipt-small">
                  <td colSpan={4}>
                    &nbsp;&nbsp;{[
                      i.hsn_code && t('receipt.hsn', { code: i.hsn_code }),
                      i.mrp && t('receipt.mrp', { mrp: i.mrp }),
                    ].filter(Boolean).join(' · ')}
                  </td>
                </tr>
              )}
              {Number(i.offer_discount) > 0 && (
                <tr>
                  <td colSpan={3}>&nbsp;&nbsp;{i.offer_name ?? t('receipt.offer')}</td>
                  <td className="num">-{money(gst.lines[n].offer)}</td>
                </tr>
              )}
              {Number(i.manual_discount) > 0 && (
                <tr>
                  <td colSpan={3}>&nbsp;&nbsp;{t('receipt.discount')}{i.manual_discount_reason ? ` (${i.manual_discount_reason})` : ''}</td>
                  <td className="num">-{money(gst.lines[n].manual)}</td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
      

      {/* Summary from the saved bill: bill lines, and the sum of their quantities (kg counted as kg). */}
      <hr />
      <div className="receipt-row receipt-items-qty">
        <span>{t('receipt.totalItems', { n: receipt.item_lines })}</span>
        <span>{t('receipt.totalQty', { qty: receipt.total_qty })}</span>
      </div>
      <hr />

      <div className="receipt-row"><span>{t('receipt.subtotal')}</span><span>{formatRupees(money(gst.subtotal))}</span></div>
      {gst.itemSavings > 0 && (
        <div className="receipt-row"><span>{t('receipt.itemSavings')}</span><span>− {formatRupees(money(gst.itemSavings))}</span></div>
      )}
      {Number(receipt.bill_offer_discount) > 0 && (
        <div className="receipt-row"><span>{receipt.bill_offer_name ?? t('receipt.billOffer')}</span><span>− {formatRupees(money(gst.billOffer))}</span></div>
      )}
      {Number(receipt.reward_discount) > 0 && (
        <div className="receipt-row"><span>{t('receipt.pointsUsed', { points: receipt.points_redeemed })}</span><span>− {formatRupees(money(gst.reward))}</span></div>
      )}
      <div className="receipt-row receipt-total"><span>{t('receipt.total')}</span><span>{formatRupees(receipt.total)}</span></div>
      {Number(receipt.total_saving) > 0 && (
        <div className="receipt-saved-box">
          {receipt.items.some((i) => i.mrp !== null)
            ? t('receipt.youSavedOnMrp', { amount: formatRupees(receipt.total_saving) })
            : t('receipt.youSavedBanner', { amount: formatRupees(receipt.total_saving) })}
        </div>
      )}
      {receipt.points_balance !== null && (
        <div className="receipt-center">
          {t('receipt.pointsLine', { earned: receipt.points_earned, balance: receipt.points_balance })}
        </div>
      )}
      <hr />

      {receipt.payments.map((p) => (
        <div key={p.id}>
          <div className="receipt-row">
            <span>{t('receipt.paid', { method: t(`methods.${p.method}`) })}</span>
            <span>{formatRupees(p.tendered ?? p.amount)}</span>
          </div>
          {p.change_due !== null && (
            <div className="receipt-row"><span>{t('receipt.change')}</span><span>{formatRupees(p.change_due)}</span></div>
          )}
          {p.reference && <div className="receipt-row"><span>{t('receipt.ref')}</span><span>{p.reference}</span></div>}
        </div>
      ))}

      {(() => {
        // Marathi bills use the Marathi footer when one is set.
        const footer = i18n.language === 'mr' && receipt.receipt_footer_mr ? receipt.receipt_footer_mr : receipt.receipt_footer;
        return footer && <footer className="receipt-center receipt-footer">{footer}</footer>;
      })()}
      <div className="receipt-center receipt-credit">{VENDOR_CREDIT}</div>
    </article>
  );
}
