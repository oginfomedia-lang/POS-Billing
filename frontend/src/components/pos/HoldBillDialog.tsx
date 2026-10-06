// Confirm holding the current bill.
import { type FormEvent, useState } from 'react';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';

interface Props {
  busy: boolean;
  error: string;
  onConfirm: (note: string) => void;
  onClose: () => void;
}

export function HoldBillDialog({ busy, error, onConfirm, onClose }: Props) {
  const [note, setNote] = useState('');
  useKeyboardShortcuts({ Escape: onClose });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onConfirm(note.trim());
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <h3>Hold Bill</h3>
        {error && <div className="form-error">{error}</div>}
        <form onSubmit={handleSubmit} className="modal-form">
          <label className="field-label">
            Note (optional)
            <input
              className="field-input"
              value={note}
              maxLength={255}
              placeholder="e.g. customer went to get wallet"
              onChange={(e) => setNote(e.target.value)}
              autoFocus
            />
          </label>
          <div className="modal-buttons">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? 'Holding…' : 'Hold Bill'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
