// Customers registered by mobile number: Udhari (Khata) balance, loyalty points, and full transaction passbooks.
import { type FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AdminNav } from '../../components/admin/AdminNav';
import { CustomerCreditLimitDialog } from '../../components/admin/CustomerCreditLimitDialog';
import { CustomerPaymentDialog } from '../../components/admin/CustomerPaymentDialog';
import {
  getCustomerCreditTransactions,
  getCustomerTransactions,
  listCustomers,
  updateCustomerName,
} from '../../services/api/customerApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { PagedResponse } from '../../types/api';
import type { CreditTxnOut, CustomerOut, RewardTxnOut } from '../../types/customer';
import { formatDateTime } from '../../utils/format';
import { formatRupees } from '../../utils/money';

type PassbookTab = 'credit' | 'loyalty';

export function CustomersPage() {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [withDues, setWithDues] = useState(false);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<PagedResponse<CustomerOut> | null>(null);
  const [selected, setSelected] = useState<CustomerOut | null>(null);
  const [passbookTab, setPassbookTab] = useState<PassbookTab>('credit');
  const [loyaltyLedger, setLoyaltyLedger] = useState<RewardTxnOut[]>([]);
  const [creditLedger, setCreditLedger] = useState<CreditTxnOut[]>([]);
  const [loadingPassbook, setLoadingPassbook] = useState(false);
  const [showPaymentDialog, setShowPaymentDialog] = useState(false);
  const [showLimitDialog, setShowLimitDialog] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  // Name editing for the selected customer (null = not editing).
  const [nameDraft, setNameDraft] = useState<string | null>(null);
  const [savingName, setSavingName] = useState(false);

  useEffect(() => { setNameDraft(null); }, [selected?.id]);

  async function saveName(e: FormEvent) {
    e.preventDefault();
    if (!selected || nameDraft === null) return;
    setSavingName(true);
    setError('');
    try {
      const updated = await updateCustomerName(selected.id, nameDraft);
      setNameDraft(null);
      setNotice(t('customers.nameUpdated'));
      setSelected(updated);
      setData((prev) => prev ? { ...prev, items: prev.items.map((c) => (c.id === updated.id ? updated : c)) } : prev);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSavingName(false);
    }
  }

  function load(p: number, dues: boolean = withDues) {
    setError('');
    listCustomers(search, p, dues)
      .then(setData)
      .catch((err) => setError(getErrorMessage(err)));
  }

  useEffect(() => {
    load(page, withDues);
  }, [page, withDues]);

  // Load passbook when selected customer or tab changes
  useEffect(() => {
    if (!selected) {
      setCreditLedger([]);
      setLoyaltyLedger([]);
      return;
    }
    let cancelled = false;
    setLoadingPassbook(true);

    if (passbookTab === 'credit') {
      getCustomerCreditTransactions(selected.id)
        .then((r) => { if (!cancelled) setCreditLedger(r.items); })
        .catch((err) => { if (!cancelled) setError(getErrorMessage(err)); })
        .finally(() => { if (!cancelled) setLoadingPassbook(false); });
    } else {
      getCustomerTransactions(selected.id)
        .then((r) => { if (!cancelled) setLoyaltyLedger(r.items); })
        .catch((err) => { if (!cancelled) setError(getErrorMessage(err)); })
        .finally(() => { if (!cancelled) setLoadingPassbook(false); });
    }

    return () => { cancelled = true; };
  }, [selected, passbookTab]);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (page === 1) load(1, withDues);
    else setPage(1);
  }

  function handlePaymentSuccess(txn: CreditTxnOut) {
    setShowPaymentDialog(false);
    setNotice(t('customers.repaymentSuccess', `Payment of ${formatRupees(Math.abs(Number(txn.amount)))} recorded successfully!`));
    if (selected) {
      const updatedBalance = txn.balance_after;
      const updatedCustomer: CustomerOut = { ...selected, credit_balance: updatedBalance };
      setSelected(updatedCustomer);
      setData((prev) =>
        prev
          ? {
              ...prev,
              items: prev.items.map((c) => (c.id === selected.id ? updatedCustomer : c)),
            }
          : prev
      );
      // Reload passbook
      getCustomerCreditTransactions(selected.id).then((r) => setCreditLedger(r.items));
    }
  }

  function handleLimitSuccess(updated: CustomerOut) {
    setShowLimitDialog(false);
    setNotice(t('customers.limitUpdated', 'Credit limit updated successfully!'));
    setSelected(updated);
    setData((prev) =>
      prev
        ? {
            ...prev,
            items: prev.items.map((c) => (c.id === updated.id ? updated : c)),
          }
        : prev
    );
  }

  return (
    <div className="admin-page customers-page">
      <AdminNav />
      <div className="admin-header">
        <h2>{t('customers.title', 'Customer Khata & Loyalty (ग्राहक व उधारी)')}</h2>
      </div>

      <div className="filter-bar" style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <form onSubmit={submit} style={{ display: 'flex', gap: 8, flex: 1, minWidth: 280 }}>
          <input
            className="field-input filter-input"
            placeholder={t('customers.searchPlaceholder', 'Search mobile or name...')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button className="btn-sm" type="submit">{t('common.filter')}</button>
        </form>

        <button
          type="button"
          className={`btn-sm ${withDues ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => { setWithDues(!withDues); setPage(1); }}
        >
          {withDues ? '✓ ' : ''}{t('customers.filterDuesOnly', 'Only with Dues (फक्त बाकी असलेले)')}
        </button>
      </div>

      {error && <div className="page-error">{error}</div>}
      {notice && (
        <div
          className="page-error"
          style={{ background: 'var(--ok-bg, #f0fdf4)', color: 'var(--ok-text, #166534)', borderColor: 'var(--ok-text, #166534)' }}
        >
          {notice}
        </div>
      )}

      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t('customers.colMobile', 'Mobile')}</th>
              <th>{t('common.name', 'Name')}</th>
              <th className="num">{t('customers.colCredit', 'Udhari Balance (बाकी)')}</th>
              <th className="num">{t('customers.colCreditLimit', 'Credit Limit')}</th>
              <th className="num">{t('customers.colPoints', 'Points')}</th>
              <th className="num">{t('customers.colVisits', 'Visits')}</th>
              <th className="num">{t('customers.colSpent', 'Total Spent')}</th>
              <th>{t('customers.colLastVisit', 'Last Visit')}</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.length === 0 && (
              <tr><td colSpan={8} className="empty-row">{t('customers.empty', 'No customers found.')}</td></tr>
            )}
            {data?.items.map((c) => {
              const dues = Number(c.credit_balance) || 0;
              return (
                <tr
                  key={c.id}
                  className={`clickable-row${selected?.id === c.id ? ' row-selected' : ''}`}
                  onClick={() => setSelected(c)}
                >
                  <td style={{ fontWeight: 600 }}>{c.mobile}</td>
                  <td>{c.name ?? '—'}</td>
                  <td className="num">
                    <strong style={{ color: dues > 0 ? 'var(--error, #dc2626)' : 'inherit' }}>
                      {formatRupees(c.credit_balance)}
                    </strong>
                  </td>
                  <td className="num" style={{ color: 'var(--text-muted, #64748b)' }}>
                    {c.credit_limit ? formatRupees(c.credit_limit) : '—'}
                  </td>
                  <td className="num">{c.points_balance}</td>
                  <td className="num">{c.visit_count}</td>
                  <td className="num">{formatRupees(c.total_spent)}</td>
                  <td className="ts-cell">{c.last_visit_at ? formatDateTime(c.last_visit_at) : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="filter-bar" style={{ marginTop: 8 }}>
          <button className="btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t('common.prev')}</button>
          <span>{t('common.pageInfo', { page, total: data.total })}</span>
          <button className="btn-sm" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>{t('common.next')}</button>
        </div>
      )}

      {selected && (
        <div style={{ marginTop: 24 }}>
          {/* Customer Detail Header & Action Buttons */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 12 }}>
            <div>
              {nameDraft === null ? (
                <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                  {selected.name ? `${selected.name} (${selected.mobile})` : selected.mobile}
                  <button type="button" className="link-button" style={{ fontSize: '0.6em', fontWeight: 500 }}
                    onClick={() => setNameDraft(selected.name ?? '')}>
                    {t(selected.name ? 'customers.editName' : 'customers.addName')}
                  </button>
                </h3>
              ) : (
                <form onSubmit={saveName} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input className="field-input" autoFocus maxLength={100} value={nameDraft}
                    placeholder={t('pay.namePlaceholder')} onChange={(e) => setNameDraft(e.target.value)} />
                  <span style={{ color: 'var(--text-muted, #64748b)' }}>{selected.mobile}</span>
                  <button type="submit" className="btn-sm btn-primary" disabled={savingName}>{t('common.save')}</button>
                  <button type="button" className="btn-sm btn-secondary" onClick={() => setNameDraft(null)}>{t('common.cancel')}</button>
                </form>
              )}
              <div style={{ fontSize: '0.9em', color: 'var(--text-muted, #64748b)', marginTop: 4 }}>
                {t('customers.colCredit', 'Udhari Balance')}:{' '}
                <strong style={{ color: Number(selected.credit_balance) > 0 ? 'var(--error, #dc2626)' : 'inherit' }}>
                  {formatRupees(selected.credit_balance)}
                </strong>
                {selected.credit_limit && ` · Limit: ${formatRupees(selected.credit_limit)}`}
                {` · Points: ${selected.points_balance}`}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                className="btn-primary"
                onClick={() => setShowPaymentDialog(true)}
              >
                {t('customers.receivePayment', 'Receive Payment (जमा नोंदवा)')}
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setShowLimitDialog(true)}
              >
                {t('customers.setLimit', 'Credit Limit (मर्यादा)')}
              </button>
            </div>
          </div>

          {/* Passbook Tabs */}
          <div className="tab-bar" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={passbookTab === 'credit'}
              className={`tab${passbookTab === 'credit' ? ' active' : ''}`}
              onClick={() => setPassbookTab('credit')}
            >
              {t('customers.tabCredit', 'Udhari Khata (उधारी खातेवही)')}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={passbookTab === 'loyalty'}
              className={`tab${passbookTab === 'loyalty' ? ' active' : ''}`}
              onClick={() => setPassbookTab('loyalty')}
            >
              {t('customers.tabLoyalty', 'Reward Points (रिवॉर्ड पॉइंट्स)')}
            </button>
          </div>

          {loadingPassbook && <div className="loading-text">{t('common.loading')}</div>}

          {/* Udhari Khata Passbook Table */}
          {passbookTab === 'credit' && !loadingPassbook && (
            <div className="table-card">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t('customers.colDate', 'Date & Time')}</th>
                    <th>{t('customers.colType', 'Type')}</th>
                    <th>{t('customers.colNote', 'Bill / Note')}</th>
                    <th>{t('pay.paymentMethod', 'Method')}</th>
                    <th className="num">{t('customers.colAmount', 'Debit / Credit')}</th>
                    <th className="num">{t('customers.colBalance', 'Balance After')}</th>
                  </tr>
                </thead>
                <tbody>
                  {creditLedger.length === 0 && (
                    <tr><td colSpan={6} className="empty-row">{t('customers.noCreditTxns', 'No credit transactions on record.')}</td></tr>
                  )}
                  {creditLedger.map((x) => {
                    const amt = Number(x.amount);
                    const isDebit = amt > 0; // customer took goods on credit
                    return (
                      <tr key={x.id}>
                        <td className="ts-cell">{formatDateTime(x.created_at)}</td>
                        <td>
                          <span
                            className="status-pill"
                            style={{
                              background: isDebit ? 'var(--warn-bg, #fef3c7)' : 'var(--ok-bg, #f0fdf4)',
                              color: isDebit ? 'var(--warn-text, #92400e)' : 'var(--ok-text, #166534)',
                            }}
                          >
                            {x.txn_type === 'udhari'
                              ? t('customers.typeUdhari', 'Sale (उधारी)')
                              : x.txn_type === 'payment'
                              ? t('customers.typePayment', 'Repayment (जमा)')
                              : x.txn_type}
                          </span>
                        </td>
                        <td>{x.note ?? '—'}</td>
                        <td style={{ textTransform: 'capitalize' }}>{x.payment_method ?? '—'}</td>
                        <td className="num" style={{ fontWeight: 600, color: isDebit ? 'var(--error, #dc2626)' : 'var(--ok-text, #166534)' }}>
                          {isDebit ? `+ ${formatRupees(x.amount)}` : `- ${formatRupees(Math.abs(amt).toFixed(2))}`}
                        </td>
                        <td className="num">
                          <strong>{formatRupees(x.balance_after)}</strong>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Loyalty Points Passbook Table */}
          {passbookTab === 'loyalty' && !loadingPassbook && (
            <div className="table-card">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t('customers.colDate', 'Date & Time')}</th>
                    <th>{t('customers.colType', 'Type')}</th>
                    <th>{t('customers.colNote', 'Bill / Note')}</th>
                    <th className="num">{t('customers.colPointsChange', 'Points Change')}</th>
                    <th className="num">{t('customers.colBalance', 'Points Balance')}</th>
                  </tr>
                </thead>
                <tbody>
                  {loyaltyLedger.length === 0 && (
                    <tr><td colSpan={5} className="empty-row">{t('customers.noTxns', 'No loyalty transactions.')}</td></tr>
                  )}
                  {loyaltyLedger.map((x) => (
                    <tr key={x.id}>
                      <td className="ts-cell">{formatDateTime(x.created_at)}</td>
                      <td>{t(`customers.types.${x.txn_type}`)}</td>
                      <td>{x.note ?? '—'}</td>
                      <td className="num">{x.points > 0 ? `+${x.points}` : x.points}</td>
                      <td className="num"><strong>{x.balance_after}</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Repayment Dialog Modal */}
      {showPaymentDialog && selected && (
        <CustomerPaymentDialog
          customer={selected}
          onClose={() => setShowPaymentDialog(false)}
          onSuccess={handlePaymentSuccess}
        />
      )}

      {/* Credit Limit Dialog Modal */}
      {showLimitDialog && selected && (
        <CustomerCreditLimitDialog
          customer={selected}
          onClose={() => setShowLimitDialog(false)}
          onSuccess={handleLimitSuccess}
        />
      )}
    </div>
  );
}
