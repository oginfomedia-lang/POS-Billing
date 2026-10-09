// Customer and reward-points types (match backend customer_schemas).

export interface CustomerOut {
  id: number;
  mobile: string;
  name: string | null;
  points_balance: number;
  lifetime_earned: number;
  lifetime_redeemed: number;
  total_spent: string;
  visit_count: number;
  first_visit_at: string | null;
  last_visit_at: string | null;
}

export type RewardTxnType = 'earn' | 'redeem' | 'reverse' | 'adjust';

/** One line of a customer's points passbook. points: + earned, − used / taken back. */
export interface RewardTxnOut {
  id: number;
  txn_type: RewardTxnType;
  points: number;
  balance_after: number;
  note: string | null;
  sale_id: number | null;
  return_id: number | null;
  created_at: string;
}
