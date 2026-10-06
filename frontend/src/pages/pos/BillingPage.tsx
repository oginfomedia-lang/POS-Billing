// Main checkout screen: scan, cart, totals, payment — Phase 2 (Dev 2).
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { useShiftStore } from '../../store/shiftStore';

export function BillingPage() {
  const { user, logout } = useAuth();
  const { shift } = useShiftStore();
  const navigate = useNavigate();

  return (
    <div className="admin-page">
      <div className="admin-header">
        <h2>POS — {user?.full_name ?? user?.username}</h2>
        <div className="admin-actions">
          {(user?.role === 'admin' || user?.role === 'manager') && (
            <button className="btn-secondary" onClick={() => navigate('/admin/users')}>Admin</button>
          )}
          <button className="btn-secondary" onClick={() => navigate('/pos/shift/close')}>Close Shift</button>
          <button className="btn-secondary" onClick={logout}>Logout</button>
        </div>
      </div>
      {shift && (
        <p className="loading-text" style={{ marginTop: 8 }}>
          Shift #{shift.id} open · Float ₹{Number(shift.opening_float).toFixed(2)}
        </p>
      )}
      <p className="loading-text">Billing screen coming in Phase 2 (Dev 2 work).</p>
    </div>
  );
}
