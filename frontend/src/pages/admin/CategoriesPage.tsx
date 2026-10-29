import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { createCategory, deleteCategory, listCategories, updateCategory } from '../../services/api/productApi';
import { getErrorMessage } from '../../services/api/httpClient';
import type { CategoryOut } from '../../types/product';
import { AdminNav } from '../../components/admin/AdminNav';
import { IconX } from '../../components/common/Icons';
import { MarathiInput } from '../../components/common/MarathiInput';

/** The category and every sub-category under it (a category can't be moved under any of these). */
function selfAndDescendants(all: CategoryOut[], id: number): Set<number> {
  const out = new Set([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const c of all) {
      if (c.parent_id !== null && out.has(c.parent_id) && !out.has(c.id)) {
        out.add(c.id);
        grew = true;
      }
    }
  }
  return out;
}

export function CategoriesPage() {
  const { t } = useTranslation();
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // null = closed, 'new' = add, a category = edit it
  const [editing, setEditing] = useState<CategoryOut | 'new' | null>(null);
  const [formName, setFormName] = useState('');
  const [formParent, setFormParent] = useState('');
  const [formActive, setFormActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const [deleting, setDeleting] = useState<CategoryOut | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState('');

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
    setEditing('new');
    setFormName(''); setFormParent(''); setFormActive(true); setFormError('');
  }

  function openEdit(c: CategoryOut) {
    setEditing(c);
    setFormName(c.name);
    setFormParent(c.parent_id !== null ? String(c.parent_id) : '');
    setFormActive(c.is_active);
    setFormError('');
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    const name = formName.trim();
    if (!name) {
      setFormError(t('categories.nameRequired'));
      return;
    }
    setSaving(true); setFormError('');
    const parent_id = formParent ? parseInt(formParent) : null;
    try {
      if (editing === 'new') await createCategory({ name, parent_id });
      else if (editing) await updateCategory(editing.id, { name, parent_id, is_active: formActive });
      setEditing(null);
      fetchCategories();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!deleting) return;
    setDeleteBusy(true); setDeleteError('');
    try {
      await deleteCategory(deleting.id);
      setDeleting(null);
      fetchCategories();
    } catch (err) {
      setDeleteError(getErrorMessage(err));
    } finally {
      setDeleteBusy(false);
    }
  }

  const blocked = editing && editing !== 'new' ? selfAndDescendants(categories, editing.id) : new Set<number>();
  const parentChoices = categories.filter((c) => !blocked.has(c.id));

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
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {categories.length === 0 && !loading && (
              <tr><td colSpan={4} className="empty-row">{t('categories.empty')}</td></tr>
            )}
            {categories.map((c) => {
              const parent = categories.find((p) => p.id === c.parent_id);
              return (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{parent?.name ?? '—'}</td>
                  <td>{c.is_active ? '✓' : '—'}</td>
                  <td className="table-actions">
                    <button className="btn-sm" onClick={() => openEdit(c)}>{t('common.edit')}</button>
                    <button className="btn-sm btn-sm-danger" onClick={() => { setDeleting(c); setDeleteError(''); }}>
                      {t('categories.delete')}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {editing && (
        <div className="modal-overlay">
          <div className="modal-box">
            <button type="button" className="modal-close-btn modal-close-corner" onClick={() => setEditing(null)} title={t('common.close')} aria-label={t('common.close')}>
              <IconX size={18} />
            </button>
            <h3>{editing === 'new' ? t('categories.addTitle') : t('categories.editTitle', { name: editing.name })}</h3>
            {formError && <div className="form-error">{formError}</div>}
            <form onSubmit={handleSave} className="modal-form">
              <label className="field-label">{t('common.name')}
                <MarathiInput className="field-input" value={formName} maxLength={100} onChange={setFormName} required autoFocus />
              </label>
              <label className="field-label">{t('categories.parent')}
                <select className="field-input" value={formParent} onChange={(e) => setFormParent(e.target.value)}>
                  <option value="">{t('categories.topLevel')}</option>
                  {parentChoices.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </label>
              {editing !== 'new' && (
                <label className="field-label checkbox-label">
                  <input type="checkbox" checked={formActive} onChange={(e) => setFormActive(e.target.checked)} />
                  {t('common.active')}
                  <span className="hint-text">{t('categories.activeHint')}</span>
                </label>
              )}
              <div className="modal-buttons">
                <button type="button" className="btn-secondary" onClick={() => setEditing(null)}>{t('common.cancel')}</button>
                <button type="submit" className="btn-primary" disabled={saving}>
                  {saving ? t('common.saving') : editing === 'new' ? t('common.create') : t('common.save')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {deleting && (
        <div className="modal-overlay">
          <div className="modal-box">
            <button type="button" className="modal-close-btn modal-close-corner" onClick={() => setDeleting(null)} title={t('common.close')} aria-label={t('common.close')}>
              <IconX size={18} />
            </button>
            <h3>{t('categories.deleteTitle', { name: deleting.name })}</h3>
            <p>{t('categories.deleteConfirm')}</p>
            {deleteError && <div className="form-error">{deleteError}</div>}
            <div className="modal-buttons">
              <button type="button" className="btn-secondary" onClick={() => setDeleting(null)}>{t('common.cancel')}</button>
              <button type="button" className="btn-danger" disabled={deleteBusy} onClick={handleDelete}>
                {deleteBusy ? t('categories.deleting') : t('categories.delete')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
