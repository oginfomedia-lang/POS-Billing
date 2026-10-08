// Confirm holding the current bill.
import { type FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { IconPauseCircle, IconX } from '../common/Icons';

interface Props {
  busy: boolean;
  error: string;
  onConfirm: (note: string) => void;
  onClose: () => void;
}

export function HoldBillDialog({ busy, error, onConfirm, onClose }: Props) {
  const { t } = useTranslation();
  const [note, setNote] = useState('');
  useKeyboardShortcuts({ Escape: onClose });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onConfirm(note.trim());
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="title-with-icon">
            <IconPauseCircle size={22} color="#d97706" />
            <h3 className="modal-title">{t('hold.title')}</h3>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose}>
            <IconX size={18} />
          </button>
        </div>

        {error && <div className="form-error">{error}</div>}

        <form onSubmit={handleSubmit} className="modal-form">
          <label className="field-label">
            <span>{t('hold.noteLabel')}</span>
            <input
              className="field-input"
              value={note}
              maxLength={255}
              placeholder={t('hold.notePlaceholder')}
              onChange={(e) => setNote(e.target.value)}
              autoFocus
            />
          </label>

          <div className="modal-buttons">
            <button type="button" className="btn-secondary" onClick={onClose}>
              {t('common.cancel')}
            </button>
            <button type="submit" className="btn-primary btn-warning-bg" disabled={busy}>
              {busy ? t('hold.holding') : t('hold.submit')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

