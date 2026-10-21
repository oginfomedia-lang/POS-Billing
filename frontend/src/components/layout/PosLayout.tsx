// Layout for POS screens: page content with the status bar at the bottom.
import { Outlet } from 'react-router-dom';
import { useOfflineSync } from '../../hooks/useOfflineSync';
import { StatusBar } from './StatusBar';

export function PosLayout() {
  useOfflineSync(); // offline catalogue refresh and upload of offline bills
  return (
    <div className="pos-layout">
      <main className="pos-content">
        <Outlet />
      </main>
      <StatusBar />
    </div>
  );
}
