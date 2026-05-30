import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { getRecords, bulkReview } from '../api';
import { useAuth } from '../AuthContext';
import { CheckCircle, XCircle, AlertTriangle, ExternalLink, RefreshCw } from 'lucide-react';

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'flagged', label: 'Flagged' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
];
const SCOPE_OPTIONS = [
  { value: '', label: 'All scopes' },
  { value: '1', label: 'Scope 1' },
  { value: '2_location', label: 'Scope 2 (Location)' },
  { value: '2_market', label: 'Scope 2 (Market)' },
  { value: '3', label: 'Scope 3' },
];
const SOURCE_OPTIONS = [
  { value: '', label: 'All sources' },
  { value: 'sap', label: 'SAP' },
  { value: 'utility', label: 'Utility' },
  { value: 'travel', label: 'Travel' },
];

function ScopeBadge({ scope }) {
  const cls = scope.startsWith('2') ? 'scope2' : scope === '1' ? 'scope1' : 'scope3';
  const label = scope === '1' ? 'S1' : scope === '2_location' ? 'S2-L' : scope === '2_market' ? 'S2-M' : 'S3';
  return <span className={`badge badge-${cls}`}>{label}</span>;
}
function SourceBadge({ src }) {
  return <span className={`badge badge-${src}`}>{src.toUpperCase()}</span>;
}
function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{status}</span>;
}

function fmtCO2(kg) {
  if (kg == null) return <span className="dim">—</span>;
  const v = parseFloat(kg);
  if (v >= 1000) return <><span className="mono">{(v / 1000).toFixed(2)}</span> <span className="dim">t</span></>;
  return <><span className="mono">{v.toFixed(1)}</span> <span className="dim">kg</span></>;
}

export default function ReviewQueue() {
  const { activeClient } = useAuth();
  const navigate = useNavigate();

  const [records, setRecords]   = useState([]);
  const [total, setTotal]       = useState(0);
  const [loading, setLoading]   = useState(true);
  const [selected, setSelected] = useState(new Set());
  const [bulkNote, setBulkNote] = useState('');
  const [bulkLoading, setBulkLoading] = useState(false);

  // Filters
  const [status, setStatus]   = useState('pending');
  const [scope, setScope]     = useState('');
  const [source, setSource]   = useState('');
  const [search, setSearch]   = useState('');
  const [page, setPage]       = useState(1);

  const PAGE_SIZE = 50;

  const load = useCallback(() => {
    if (!activeClient) return;
    setLoading(true);
    getRecords({
      client_id: activeClient.id,
      review_status: status || undefined,
      scope: scope || undefined,
      source_type: source || undefined,
      search: search || undefined,
      page,
    })
      .then(data => {
        setRecords(data.results || data);
        setTotal(data.count || (data.results || data).length);
      })
      .finally(() => setLoading(false));
  }, [activeClient, status, scope, source, search, page]);

  useEffect(() => { load(); }, [load]);

  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };
  const toggleAll = () => {
    if (selected.size === records.length) setSelected(new Set());
    else setSelected(new Set(records.map(r => r.id)));
  };

  const doBulk = async (action) => {
    if (selected.size === 0) return;
    setBulkLoading(true);
    try {
      await bulkReview([...selected], action, bulkNote);
      setSelected(new Set());
      setBulkNote('');
      load();
    } finally {
      setBulkLoading(false);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Review Queue</h1>
          <div className="subtitle">Inspect, flag, approve or reject emission records before audit lock</div>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={load}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      <div className="page-body">
        {/* Filters */}
        <div className="filters-bar">
          <span className="filter-label">Filter:</span>
          <select className="filter-select" value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}>
            {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <select className="filter-select" value={scope} onChange={e => { setScope(e.target.value); setPage(1); }}>
            {SCOPE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <select className="filter-select" value={source} onChange={e => { setSource(e.target.value); setPage(1); }}>
            {SOURCE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <input
            className="search-input"
            placeholder="Search location, traveler, doc#…"
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1); }}
          />
          <span className="filter-label" style={{ marginLeft: 'auto' }}>
            {total} record{total !== 1 ? 's' : ''}
          </span>
        </div>

        {/* Bulk action bar */}
        {selected.size > 0 && (
          <div className="bulk-bar">
            <span className="bulk-count">{selected.size} selected</span>
            <input
              className="search-input"
              placeholder="Optional note…"
              value={bulkNote}
              onChange={e => setBulkNote(e.target.value)}
              style={{ width: 180 }}
            />
            <button className="btn btn-approve" onClick={() => doBulk('approve')} disabled={bulkLoading}>
              <CheckCircle size={13} /> Approve
            </button>
            <button className="btn btn-flag" onClick={() => doBulk('flag')} disabled={bulkLoading}>
              <AlertTriangle size={13} /> Flag
            </button>
            <button className="btn btn-reject" onClick={() => doBulk('reject')} disabled={bulkLoading}>
              <XCircle size={13} /> Reject
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => setSelected(new Set())} style={{ marginLeft: 'auto' }}>
              Clear
            </button>
          </div>
        )}

        {loading
          ? <div className="loading"><div className="spinner" /><span>Loading records…</span></div>
          : records.length === 0
            ? (
              <div className="empty-state">
                <CheckCircle size={48} />
                <h3>No records match your filters</h3>
                <p>Try clearing filters or uploading new data.</p>
              </div>
            )
            : (
              <div className="table-wrapper">
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th className="checkbox-cell">
                          <input type="checkbox" checked={selected.size === records.length && records.length > 0} onChange={toggleAll} />
                        </th>
                        <th>Status</th>
                        <th>Scope</th>
                        <th>Source</th>
                        <th>Activity</th>
                        <th>Date</th>
                        <th>Location / Traveler</th>
                        <th>CO₂e</th>
                        <th>Flags</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {records.map(r => (
                        <tr key={r.id} className={r.is_flagged ? 'flagged' : ''}>
                          <td className="checkbox-cell">
                            <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggleSelect(r.id)} />
                          </td>
                          <td><StatusBadge status={r.review_status} /></td>
                          <td><ScopeBadge scope={r.scope} /></td>
                          <td><SourceBadge src={r.source_type} /></td>
                          <td>
                            <div style={{ fontSize: 12, color: 'var(--text)' }}>{r.activity_type_display}</div>
                            <div style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--mono)' }}>
                              {r.canonical_value} {r.canonical_unit}
                            </div>
                          </td>
                          <td className="mono dim">{r.activity_date}</td>
                          <td>
                            <div style={{ fontSize: 12 }}>
                              {r.traveler_name || r.location_name || r.meter_id || <span className="dim">—</span>}
                            </div>
                            {r.travel_origin && r.travel_destination && (
                              <div style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--mono)' }}>
                                {r.travel_origin} → {r.travel_destination}
                              </div>
                            )}
                          </td>
                          <td style={{ textAlign: 'right' }}>{fmtCO2(r.co2e_kg)}</td>
                          <td>
                            {r.is_flagged && (
                              <span title={r.flag_reasons?.join(', ')}>
                                <AlertTriangle size={14} color="var(--amber)" />
                              </span>
                            )}
                          </td>
                          <td>
                            <button
                              className="btn btn-ghost btn-sm"
                              onClick={() => navigate(`/review/${r.id}`)}
                              title="View detail"
                            >
                              <ExternalLink size={12} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )
        }

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="gap-8" style={{ marginTop: 16, justifyContent: 'center' }}>
            <button className="btn btn-ghost btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
            <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>Page {page} of {totalPages}</span>
            <button className="btn btn-ghost btn-sm" disabled={page === totalPages} onClick={() => setPage(p => p + 1)}>Next →</button>
          </div>
        )}
      </div>
    </>
  );
}
