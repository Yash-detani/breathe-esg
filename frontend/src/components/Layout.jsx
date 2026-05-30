import React from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import {
  LayoutDashboard, ClipboardCheck, Upload, Database,
  LogOut, ChevronDown, Leaf
} from 'lucide-react';

export default function Layout() {
  const { user, clients, activeClient, switchClient, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="gap-4">
            <Leaf size={16} color="var(--green)" />
            <span className="wordmark">Breathe ESG</span>
          </div>
          <div className="sub">Emissions Platform</div>
        </div>

        {/* Client selector */}
        {clients.length > 1 && (
          <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)' }}>
            <select
              className="filter-select"
              style={{ width: '100%', fontSize: '12px' }}
              value={activeClient?.id || ''}
              onChange={e => {
                const c = clients.find(x => x.id === e.target.value);
                if (c) switchClient(c);
              }}
            >
              {clients.map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
        )}
        {clients.length === 1 && (
          <div style={{ padding: '8px 20px', borderBottom: '1px solid var(--border)' }}>
            <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>Client</div>
            <div style={{ fontSize: '12px', color: 'var(--text)', fontWeight: 500 }}>
              {activeClient?.name}
            </div>
          </div>
        )}

        <nav className="sidebar-nav">
          <div className="nav-section-label">Overview</div>
          <NavLink to="/dashboard" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <LayoutDashboard size={15} /> Dashboard
          </NavLink>

          <div className="nav-section-label" style={{ marginTop: 8 }}>Workflow</div>
          <NavLink to="/review" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <ClipboardCheck size={15} /> Review Queue
          </NavLink>
          <NavLink to="/upload" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <Upload size={15} /> Upload Data
          </NavLink>
          <NavLink to="/batches" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <Database size={15} /> Ingestion Batches
          </NavLink>
        </nav>

        <div className="sidebar-footer">
          <div className="user-name">{user?.first_name || user?.username}</div>
          <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>{user?.email}</div>
          <button className="logout-btn" onClick={handleLogout}>
            <span className="gap-4"><LogOut size={12} /> Sign out</span>
          </button>
        </div>
      </aside>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
