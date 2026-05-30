import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend
} from 'recharts';
import { getDashboard } from '../api';
import { useAuth } from '../AuthContext';
import { AlertTriangle, CheckCircle, Clock, Database, TrendingUp } from 'lucide-react';

const SCOPE_COLORS = {
  '1': '#c084fc',
  '2_location': '#60a5fa',
  '2_market': '#38bdf8',
  '3': '#fb923c',
};
const SCOPE_LABELS = {
  '1': 'Scope 1',
  '2_location': 'Scope 2 (Location)',
  '2_market': 'Scope 2 (Market)',
  '3': 'Scope 3',
};
const SOURCE_COLORS = {
  sap: '#4ade80',
  utility: '#60a5fa',
  travel: '#d8b4fe',
};

function fmt(n, decimals = 1) {
  if (n == null) return '—';
  if (n >= 1000) return (n / 1000).toFixed(decimals) + 'k';
  return Number(n).toFixed(decimals);
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--surface2)', border: '1px solid var(--border2)',
      borderRadius: 4, padding: '8px 12px', fontSize: 12
    }}>
      <div style={{ color: 'var(--text-dim)', marginBottom: 4 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color }}>
          {p.name}: {fmt(p.value)} tCO₂e
        </div>
      ))}
    </div>
  );
};

export default function Dashboard() {
  const { activeClient } = useAuth();
  const [data, setData]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [year, setYear]   = useState(new Date().getFullYear());
  const navigate = useNavigate();

  useEffect(() => {
    if (!activeClient) return;
    setLoading(true);
    getDashboard(activeClient.id, year)
      .then(setData)
      .finally(() => setLoading(false));
  }, [activeClient, year]);

  if (loading) return <div className="loading"><div className="spinner" /><span>Loading dashboard…</span></div>;
  if (!data) return <div className="loading">No data available.</div>;

  const scopeData = (data.scope_breakdown || []).map(s => ({
    name: SCOPE_LABELS[s.scope] || s.scope,
    value: parseFloat(s.total_co2e || 0) / 1000,
    color: SCOPE_COLORS[s.scope] || '#888',
    count: s.count,
  }));

  const sourceData = (data.source_breakdown || []).map(s => ({
    name: s.source_type.toUpperCase(),
    co2e: parseFloat(s.total_co2e || 0) / 1000,
    count: s.count,
    color: SOURCE_COLORS[s.source_type] || '#888',
  }));

  const totalTonnes = (data.total_co2e_tonnes || 0).toFixed(1);
  const pending = data.pending_count || 0;
  const flagged = data.flagged_count || 0;
  const approved = data.approved_count || 0;
  const total = data.total_records || 0;
  const approvalRate = total ? ((approved / total) * 100).toFixed(0) : 0;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <div className="subtitle">{activeClient?.name} · Reporting Year {year}</div>
        </div>
        <div className="gap-8">
          <select className="filter-select" value={year} onChange={e => setYear(Number(e.target.value))}>
            {[2024, 2023, 2022].map(y => <option key={y}>{y}</option>)}
          </select>
          <button className="btn btn-primary" onClick={() => navigate('/upload')}>
            + Upload Data
          </button>
        </div>
      </div>

      <div className="page-body">
        {/* Stat cards */}
        <div className="stat-grid">
          <div className="card">
            <div className="card-label">Total Emissions</div>
            <div className="card-value">{fmt(data.total_co2e_tonnes, 1)}</div>
            <div className="card-sub">tCO₂e · {year}</div>
          </div>
          <div className="card">
            <div className="card-label">Records Total</div>
            <div className="card-value">{total}</div>
            <div className="card-sub">emission records ingested</div>
          </div>
          <div className="card">
            <div className="card-label">Pending Review</div>
            <div className={`card-value ${pending > 0 ? 'amber' : 'green'}`}>{pending}</div>
            <div className="card-sub">awaiting analyst sign-off</div>
          </div>
          <div className="card">
            <div className="card-label">Flagged</div>
            <div className={`card-value ${flagged > 0 ? 'red' : 'green'}`}>{flagged}</div>
            <div className="card-sub">need attention before audit</div>
          </div>
          <div className="card">
            <div className="card-label">Approval Rate</div>
            <div className={`card-value ${approvalRate >= 80 ? 'green' : 'amber'}`}>{approvalRate}%</div>
            <div className="card-sub">{approved} approved of {total}</div>
          </div>
        </div>

        {/* Charts */}
        <div className="chart-row">
          <div className="chart-card">
            <h3>Emissions by Scope (tCO₂e)</h3>
            {scopeData.length === 0
              ? <div style={{ color: 'var(--text-dim)', fontSize: 12, padding: '20px 0' }}>No records for this period.</div>
              : <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={scopeData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, value }) => `${value.toFixed(1)}t`}>
                      {scopeData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                    </Pie>
                    <Tooltip formatter={(v) => [`${v.toFixed(2)} tCO₂e`]} contentStyle={{ background: 'var(--surface2)', border: '1px solid var(--border2)', fontSize: 12 }} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
            }
          </div>

          <div className="chart-card">
            <h3>Emissions by Source (tCO₂e)</h3>
            {sourceData.length === 0
              ? <div style={{ color: 'var(--text-dim)', fontSize: 12, padding: '20px 0' }}>No records for this period.</div>
              : <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={sourceData} margin={{ left: -10 }}>
                    <XAxis dataKey="name" tick={{ fill: 'var(--text-dim)', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: 'var(--text-dim)', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar dataKey="co2e" radius={[3, 3, 0, 0]}>
                      {sourceData.map((s, i) => <Cell key={i} fill={s.color} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
            }
          </div>
        </div>

        {/* Review status + recent batches */}
        <div className="chart-row">
          <div className="chart-card">
            <h3>Review Status</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 8 }}>
              {[
                { label: 'Approved', count: approved, color: 'var(--green)', max: total },
                { label: 'Pending', count: pending, color: 'var(--amber)', max: total },
                { label: 'Flagged', count: flagged, color: 'var(--red)', max: total },
              ].map(({ label, count, color, max }) => (
                <div key={label}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                    <span style={{ color: 'var(--text-dim)' }}>{label}</span>
                    <span style={{ fontFamily: 'var(--mono)', color }}>{count}</span>
                  </div>
                  <div className="progress-bar">
                    <div className="progress-fill" style={{
                      width: max ? `${(count / max) * 100}%` : '0%',
                      background: color
                    }} />
                  </div>
                </div>
              ))}
            </div>
            <button
              className="btn btn-ghost btn-sm"
              style={{ marginTop: 16, width: '100%', justifyContent: 'center' }}
              onClick={() => navigate('/review')}
            >
              Open Review Queue →
            </button>
          </div>

          <div className="chart-card">
            <h3>Recent Ingestion Batches</h3>
            {(data.recent_batches || []).length === 0
              ? <div style={{ color: 'var(--text-dim)', fontSize: 12 }}>No batches yet.</div>
              : (data.recent_batches || []).map(b => (
                  <div key={b.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--border)', fontSize: 12 }}>
                    <span className={`badge badge-${b.source_type}`} style={{ fontSize: 10 }}>
                      {b.source_type.toUpperCase()}
                    </span>
                    <span className="truncate" style={{ flex: 1, color: 'var(--text)', maxWidth: 160 }}>{b.original_filename}</span>
                    <span style={{ fontFamily: 'var(--mono)', color: 'var(--green)', fontSize: 11 }}>
                      {b.success_rows}↑
                    </span>
                    {b.failed_rows > 0 && <span style={{ fontFamily: 'var(--mono)', color: 'var(--red)', fontSize: 11 }}>{b.failed_rows}✕</span>}
                  </div>
                ))
            }
            <button
              className="btn btn-ghost btn-sm"
              style={{ marginTop: 12, width: '100%', justifyContent: 'center' }}
              onClick={() => navigate('/batches')}
            >
              View all batches →
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
