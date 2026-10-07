// One printable price/barcode sticker.
import { useTranslation } from 'react-i18next';
import type { BarPattern } from '../../utils/barcode';
import { formatRupees } from '../../utils/money';

const QUIET_ZONE = 9; // blank modules each side so scanners find the edges

interface Props {
  name: string;
  /** Price the customer pays per unit (tax-inclusive). */
  price: string | null;
  code: string;
  pattern: BarPattern;
}

export function BarcodeSvg({ pattern }: { pattern: BarPattern }) {
  const width = pattern.modules.length + QUIET_ZONE * 2;
  const bars: { x: number; w: number }[] = [];
  for (let i = 0; i < pattern.modules.length; i++) {
    if (pattern.modules[i] !== '1') continue;
    const last = bars[bars.length - 1];
    if (last && last.x + last.w === i + QUIET_ZONE) last.w += 1;
    else bars.push({ x: i + QUIET_ZONE, w: 1 });
  }
  return (
    <svg className="label-bars" viewBox={`0 0 ${width} 40`} preserveAspectRatio="none" aria-hidden="true">
      <rect width={width} height="40" fill="#fff" />
      {bars.map((b) => <rect key={b.x} x={b.x} width={b.w} height="40" fill="#000" />)}
    </svg>
  );
}

export function BarcodeLabel({ name, price, code, pattern }: Props) {
  const { t } = useTranslation();
  return (
    <div className="barcode-label">
      <div className="label-name">{name}</div>
      {price !== null && <div className="label-price">{formatRupees(price)} <span>{t('labels.inclGst')}</span></div>}
      <BarcodeSvg pattern={pattern} />
      <div className="label-digits">{code}</div>
    </div>
  );
}
