// Layout for POS screens: page content with the status bar at the bottom.
import { Outlet } from 'react-router-dom';
import { StatusBar } from './StatusBar';

export function PosLayout() {
  return (
    <div className="pos-layout">
      <main className="pos-content">
        <Outlet />
      </main>
      <StatusBar />
    </div>
  );
}
