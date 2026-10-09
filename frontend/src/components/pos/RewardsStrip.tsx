// Under the customer mobile on the payment screen: points balance and the Redeem control.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getRewards } from '../../services/api/billingApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { RewardInfo } from '../../types/sale';
import { formatRupees } from '../../utils/money';
import { IconSparkles } from '../common/Icons';

interface Props {
  /** Mobile saved on the bill (null = none yet). */
  mobile: string | null;
  /** Points already reserved on this bill. */
  pointsRedeemed: number;
  /** Bill amount before GST that the reward can come off (subtotal − other discounts), to cap the blocks. */
  roomForReward: number;
  onRedeem: (blocks: number) => Promise<void>;
  disabled: boolean;
}

export function RewardsStrip({ mobile, pointsRedeemed, roomForReward, onRedeem, disabled }: Props) {
  const { t } = useTranslation();
  const [info, setInfo] = useState<RewardInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setInfo(null);
    setError('');
    if (!mobile) return;
    let cancelled = false;
    getRewards(mobile)
      .then((r) => { if (!cancelled) setInfo(r); })
      .catch((err) => { if (!cancelled) setError(getErrorMessage(err)); });
    return () => { cancelled = true; };
  }, [mobile]);

  if (!mobile || !info?.enabled) return error ? <div className="form-error">{error}</div> : null;

  const blockValue = Number(info.block_value);
  const current = Math.floor(pointsRedeemed / info.block_points);
  const maxBlocks = Math.min(info.max_blocks, Math.floor(roomForReward / blockValue));

  async function redeem(blocks: number) {
    setBusy(true);
    setError('');
    try {
      await onRedeem(blocks);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rewards-strip">
      <span className="rewards-balance">
        <IconSparkles size={14} />
        {info.registered ? t('rewards.balance', { points: info.points_balance }) : t('rewards.newCustomer')}
      </span>
      {(maxBlocks > 0 || current > 0) && (
        <div className="rewards-redeem">
          {current > 0 && (
            <button type="button" className="btn-sm" disabled={busy || disabled} onClick={() => redeem(current - 1)}>−</button>
          )}
          <span>
            {current > 0
              ? t('rewards.using', { points: pointsRedeemed, amount: formatRupees(current * blockValue) })
              : t('rewards.canRedeem', { points: info.block_points, amount: formatRupees(info.block_value) })}
          </span>
          <button type="button" className="btn-sm" disabled={busy || disabled || current >= maxBlocks} onClick={() => redeem(current + 1)}>
            {current > 0 ? '+' : t('rewards.redeem')}
          </button>
        </div>
      )}
      {error && <div className="form-error">{error}</div>}
    </div>
  );
}
