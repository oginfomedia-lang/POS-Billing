// POS billing screen — Phase 2 placeholder.
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
      <p className="loading-text">Billing screen coming in Phase 2.</p>
    </div>
  );
}
