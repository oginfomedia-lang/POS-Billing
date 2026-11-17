// Accounting (Tally): ledger names, vouchers, GST summary.

/** Exact ledger names in the shop's Tally company. {rate} = GST rate, {half} = half of it (CGST / SGST). */
export interface TallyLedgers {
  cash: string;
  upi: string;
  card: string;
  bank: string;
  udhari: string; // customers on khata (Sundry Debtors)
  sales: string;
  sales_return: string;
  purchase: string;
  purchase_return: string;
  output_cgst: string;
  output_sgst: string;
  input_cgst: string;
  input_sgst: string;
  input_igst: string;
  freight: string;
  round_off: string;
}

export type VoucherType = 'sales' | 'credit_note' | 'receipt' | 'purchase' | 'payment' | 'debit_note';

export interface VoucherLine {
  ledger: string;
  debit: string;
  credit: string;
}

export interface VoucherOut {
  guid: string;
  voucher_type: VoucherType;
  number: string;
  date: string;
  store_id: number | null;
  party: string;
  party_gstin: string | null;
  reference: string | null;
  narration: string;
  lines: VoucherLine[];
  total_amount: string;
}

export interface DayBookOut {
  date_from: string;
  date_to: string;
  store_id: number | null;
  vouchers: VoucherOut[];
  warnings: string[];
  counts: Partial<Record<VoucherType, number>>;
}

export interface GstHeadRow {
  tax_rate: string;
  taxable: string;
  cgst: string;
  sgst: string;
  igst: string;
}

export interface GstSummaryOut {
  date_from: string;
  date_to: string;
  store_id: number | null;
  output: GstHeadRow[];
  input: GstHeadRow[];
  output_total: GstHeadRow;
  input_total: GstHeadRow;
  net_cgst: string;
  net_sgst: string;
  net_igst: string;
  net_payable: string;
  warnings: string[];
}
