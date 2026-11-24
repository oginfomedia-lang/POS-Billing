// Customer and reward-points types (match backend customer_schemas).

export interface CustomerOut {
  id: number;
  mobile: string;
  name: string | null;
  points_balance: number;
  credit_balance: string;
  credit_limit: string | null;
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

export interface CustomerCreditInfo {
  mobile: string;
  name: string | null;
  registered: boolean;
  credit_balance: string;
  credit_limit: string | null;
  available_credit: string | null;
}

export type CreditTxnType = 'udhari' | 'payment' | 'return' | 'adjust';

export interface CreditTxnOut {
  id: number;
  txn_type: CreditTxnType;
  amount: string;
  balance_after: string;
  payment_method: string | null;
  reference: string | null;
  note: string | null;
  sale_id: number | null;
  return_id: number | null;
  shift_id: number | null; // cash taken at a counter with an open shift: it is in that drawer
  created_at: string;
}

export interface CreditRepaymentRequest {
  amount: string;
  payment_method: 'cash' | 'upi' | 'card' | 'bank';
  reference?: string;
  note?: string;
  store_id?: number; // head office only: the store that received the money
}
