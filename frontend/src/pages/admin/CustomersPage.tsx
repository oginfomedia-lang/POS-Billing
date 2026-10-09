// Customers registered by mobile number: points balance, visits, and each customer's points passbook.
import { type FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AdminNav } from '../../components/admin/AdminNav';
import { getErrorMessage } from '../../services/api/httpClient';
import { getCustomerTransactions, listCustomers } from '../../services/api/customerApi';
import type { PagedResponse } from '../../types/api';
import type { CustomerOut, RewardTxnOut } from '../../types/customer';
import { formatDateTime } from '../../utils/format';
import { formatRupees } from '../../utils/money';

export function CustomersPage() {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<PagedResponse<CustomerOut> | null>(null);
  const [selected, setSelected] = useState<CustomerOut | null>(null);
  const [ledger, setLedger] = useState<RewardTxnOut[]>([]);
  const [error, setError] = useState('');

  function load(p: number) {
    setError('');
    listCustomers(search, p).then(setData).catch((err) => setError(getErrorMessage(err)));
  }

  useEffect(() => { load(page); }, [page]);

  useEffect(() => {
    setLedger([]);
    if (!selected) return;
    let cancelled = false;
    getCustomerTransactions(selected.id)
      .then((r) => { if (!cancelled) setLedger(r.items); })
      .catch((err) => { if (!cancelled) setError(getErrorMessage(err)); });
    return () => { cancelled = true; };
  }, [selected]);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (page === 1) load(1);
    else setPage(1);
  }

  return (
    <div className="admin-page customers-page">
      <AdminNav />
      <div className="admin-header"><h2>{t('customers.title')}</h2></div>

      <form className="filter-bar" onSubmit={submit}>
        <input
          className="field-input filter-input"
          placeholder={t('customers.searchPlaceholder')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button className="btn-sm" type="submit">{t('common.filter')}</button>
      </form>
      {error && <div className="page-error">{error}</div>}

      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t('customers.colMobile')}</th>
              <th>{t('common.name')}</th>
              <th className="num">{t('customers.colPoints')}</th>
              <th className="num">{t('customers.colVisits')}</th>
              <th className="num">{t('customers.colSpent')}</th>
              <th>{t('customers.colLastVisit')}</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.length === 0 && <tr><td colSpan={6} className="empty-row">{t('customers.empty')}</td></tr>}
            {data?.items.map((c) => (
              <tr
                key={c.id}
                className={`clickable-row${selected?.id === c.id ? ' row-selected' : ''}`}
                onClick={() => setSelected(c)}
              >
                <td>{c.mobile}</td>
                <td>{c.name ?? '—'}</td>
                <td className="num"><strong>{c.points_balance}</strong></td>
                <td className="num">{c.visit_count}</td>
                <td className="num">{formatRupees(c.total_spent)}</td>
                <td className="ts-cell">{c.last_visit_at ? formatDateTime(c.last_visit_at) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data && data.pages > 1 && (
        <div className="filter-bar">
          <button className="btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t('common.prev')}</button>
          <span>{t('common.pageInfo', { page, total: data.total })}</span>
          <button className="btn-sm" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>{t('common.next')}</button>
        </div>
      )}

      {selected && (
        <>
          <h3 className="section-title">{t('customers.passbook', { mobile: selected.mobile })}</h3>
          <div className="table-card">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('customers.colDate')}</th>
                  <th>{t('customers.colType')}</th>
                  <th>{t('customers.colNote')}</th>
                  <th className="num">{t('customers.colPointsChange')}</th>
                  <th className="num">{t('customers.colBalance')}</th>
                </tr>
              </thead>
              <tbody>
                {ledger.length === 0 && <tr><td colSpan={5} className="empty-row">{t('customers.noTxns')}</td></tr>}
                {ledger.map((x) => (
                  <tr key={x.id}>
                    <td className="ts-cell">{formatDateTime(x.created_at)}</td>
                    <td>{t(`customers.types.${x.txn_type}`)}</td>
                    <td>{x.note ?? '—'}</td>
                    <td className="num">{x.points > 0 ? `+${x.points}` : x.points}</td>
                    <td className="num">{x.balance_after}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
