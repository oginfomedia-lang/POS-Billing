// POS home: entry point to billing, held bills and shift.
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

export function PosPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="admin-page">
      <div className="admin-header">
        <h2>POS — {user?.full_name ?? user?.username}</h2>
        <div className="admin-actions">
          {(user?.role === 'admin' || user?.role === 'manager') && (
            <button className="btn-secondary" onClick={() => navigate('/admin/users')}>
              Admin
            </button>
          )}
          <button className="btn-secondary" onClick={logout}>Logout</button>
        </div>
      </div>
      <div className="pos-menu">
        <button className="btn-primary" onClick={() => navigate('/pos/billing')}>Start Billing</button>
        <button className="btn-secondary" onClick={() => navigate('/pos/held')}>Held Bills</button>
        <button className="btn-secondary" onClick={() => navigate('/pos/open-shift')}>Open Shift</button>
      </div>
    </div>
  );
}
