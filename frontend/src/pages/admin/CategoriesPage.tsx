import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { createCategory, listCategories } from '../../services/api/productApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { CategoryOut } from '../../types/product';
import { AdminNav } from '../../components/admin/AdminNav';

export function CategoriesPage() {
  const { t } = useTranslation();
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [modal, setModal] = useState(false);
  const [formName, setFormName] = useState('');
  const [formParent, setFormParent] = useState('');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  async function fetchCategories() {
    setLoading(true);
    setError('');
    try {
      setCategories(await listCategories());
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchCategories(); }, []);

  function openCreate() {
    setModal(true);
    setFormName(''); setFormParent(''); setFormError('');
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true); setFormError('');
    try {
      await createCategory({
        name: formName,
        parent_id: formParent ? parseInt(formParent) : null,
      });
      setModal(false);
      fetchCategories();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="admin-page">
      <AdminNav />
      <div className="admin-header">
        <h2>{t('categories.title')}</h2>
        <div className="admin-actions">
          <button className="btn-primary" onClick={openCreate}>{t('categories.add')}</button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">{t('common.loading')}</div>}

      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t('common.name')}</th><th>{t('categories.colParent')}</th><th>{t('common.active')}</th>
            </tr>
          </thead>
          <tbody>
            {categories.map((c) => {
              const parent = categories.find((p) => p.id === c.parent_id);
              return (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{parent?.name ?? '—'}</td>
                  <td>{c.is_active ? '✓' : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3>{t('categories.addTitle')}</h3>
            {formError && <div className="form-error">{formError}</div>}
            <form onSubmit={handleCreate} className="modal-form">
              <label className="field-label">{t('common.name')}
                <input className="field-input" value={formName} onChange={(e) => setFormName(e.target.value)} required />
              </label>
              <label className="field-label">{t('categories.parent')}
                <select className="field-input" value={formParent} onChange={(e) => setFormParent(e.target.value)}>
                  <option value="">{t('categories.topLevel')}</option>
                  {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </label>
              <div className="modal-buttons">
                <button type="button" className="btn-secondary" onClick={() => setModal(false)}>{t('common.cancel')}</button>
                <button type="submit" className="btn-primary" disabled={saving}>{saving ? t('common.saving') : t('common.create')}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
