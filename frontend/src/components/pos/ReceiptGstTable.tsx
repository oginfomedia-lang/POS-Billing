// Rate-wise GST table printed at the bottom of a bill or credit note (taxable value, CGST, SGST).
import { useTranslation } from 'react-i18next';
import type { GstSummaryRow } from '../../types/sale';

export function ReceiptGstTable({ rows }: { rows: GstSummaryRow[] }) {
  const { t } = useTranslation();
  if (rows.length === 0) return null;
  return (
    <>
      <div className="receipt-center receipt-small">{t('receipt.gstSummary')}</div>
      <table className="receipt-items receipt-gst-table">
        <thead>
          <tr>
            <th>{t('receipt.gstRate')}</th>
            <th className="num">{t('receipt.taxable')}</th>
            <th className="num">{t('receipt.cgst')}</th>
            <th className="num">{t('receipt.sgst')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.tax_rate}>
              <td>{Number(r.tax_rate)}%</td>
              <td className="num">{r.taxable}</td>
              <td className="num">{r.cgst}</td>
              <td className="num">{r.sgst}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
