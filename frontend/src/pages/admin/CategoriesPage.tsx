import { useEffect, useState } from 'react';
import { createCategory, listCategories } from '../../services/api/productApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { CategoryOut } from '../../types/product';
import { AdminNav } from '../../components/admin/AdminNav';

export function CategoriesPage() {
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
        <h2>Categories</h2>
        <div className="admin-actions">
          <button className="btn-primary" onClick={openCreate}>+ Add Category</button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}
      {loading && <div className="loading-text">Loading…</div>}

      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th><th>Parent</th><th>Active</th>
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

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3>Add Category</h3>
            {formError && <div className="form-error">{formError}</div>}
            <form onSubmit={handleCreate} className="modal-form">
              <label className="field-label">Name
                <input className="field-input" value={formName} onChange={(e) => setFormName(e.target.value)} required />
              </label>
              <label className="field-label">Parent Category
                <select className="field-input" value={formParent} onChange={(e) => setFormParent(e.target.value)}>
                  <option value="">— None (top level) —</option>
                  {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </label>
              <div className="modal-buttons">
                <button type="button" className="btn-secondary" onClick={() => setModal(false)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Create'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
