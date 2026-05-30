import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getBatches, getBatchFailedRows } from '../api';
import { useAuth } from '../AuthContext';
import { Database, ChevronDown, ChevronRight, AlertTriangle, CheckCircle, XCircle, Clock } from 'lucide-react';

function StatusIcon({ status }) {
  if (status === 'complete') return <CheckCircle size={14} color="var(--green)" />;
  if (status === 'failed')   return <XCircle size={14} color="var(--red)" />;
  if (status === 'partial')  return <AlertTriangle size={14} color="var(--amber)" />;
  return <Clock size={14} color="var(--text-dim)" />;
}

function BatchRow({ batch }) {
  const [expanded, setExpanded] = useState(false);
  const [failedRows, setFailedRows] = useState(null);
  const navigate = useNavigate();

  const loadFailed = async () => {
    if (failedRows) return;
    const rows = await getBatchFailedRows(batch.id);
    setFailedRows(rows);
  };

  const toggle = () => {
    setExpanded(e => !e);
    if (!expanded) loadFailed();
  };

  return (
    <>
      <tr style={{ cursor: 'pointer' }} onClick={toggle}>
        <td>
          <div className="gap-4">
            {expanded ? <ChevronDown size={13} color="var(--text-dim)" /> : <ChevronRight size={13} color="var(--text-dim)" />}
            <StatusIcon status={batch.status} />
          </div>
        </td>
        <td>
          <span className={`badge badge-${batch.source_type}`}>{batch.source_type.toUpperCase()}</span>
        </td>
        <td>
          <div className="mono" style={{ fontSize: 12 }}>{batch.original_filename || '—'}</div>
          <div style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--mono)' }}>
            {batch.id.slice(0, 8)}…
          </div>
        </td>
        <td className="mono dim" style={{ fontSize: 12 }}>{new Date(batch.uploaded_at).toLocaleString()}</td>
        <td style={{ fontSize: 12, color: 'var(--text-dim)' }}>{batch.uploaded_by?.username || '—'}</td>
        <td style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>
          {batch.period_start && batch.period_end
            ? `${batch.period_start} → ${batch.period_end}`
            : '—'}
        </td>
        <td>
          <div className="batch-counts">
            <span className="ok">{batch.success_rows}↑</span>
            {batch.failed_rows > 0 && <span className="fail">{batch.failed_rows}✕</span>}
            {batch.flagged_rows > 0 && <span className="flag">{batch.flagged_rows}⚑</span>}
          </div>
        </td>
        <td>
          <span className={`badge badge-${batch.status === 'complete' ? 'approved' : batch.status === 'failed' ? 'rejected' : 'flagged'}`}>
            {batch.status_display}
          </span>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={8} style={{ background: 'var(--surface2)', padding: 0 }}>
            <div style={{ padding: '12px 20px' }}>
              {/* Parse errors */}
              {batch.error_log?.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-dim)', marginBottom: 6 }}>
                    Parse errors ({batch.error_log.length})
                  </div>
                  <div style={{ maxHeight: 140, overflowY: 'auto', fontFamily: 'var(--mono)', fontSize: 11 }}>
                    {batch.error_log.map((e, i) => (
                      <div key={i} style={{ padding: '3px 0', borderBottom: '1px solid var(--border)', color: 'var(--red)' }}>
                        Row {e.row}: <span style={{ color: 'var(--text)' }}>{e.message}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {/* Failed rows detail */}
              {failedRows && failedRows.length > 0 && (
                <div>
                  <div style={{ fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-dim)', marginBottom: 6 }}>
                    Failed rows with raw data
                  </div>
                  {failedRows.map(fr => (
                    <div key={fr.id} style={{ padding: '6px 0', borderBottom: '1px solid var(--border)', fontSize: 11 }}>
                      <span style={{ fontFamily: 'var(--mono)', color: 'var(--amber)' }}>Row {fr.row_number}</span>
                      <span style={{ color: 'var(--red)', margin: '0 8px' }}>{fr.error_message}</span>
                      <span style={{ fontFamily: 'var(--mono)', color: 'var(--text-dim)' }}>
                        {JSON.stringify(fr.raw_data).slice(0, 120)}…
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {failedRows && failedRows.length === 0 && batch.error_log?.length === 0 && (
                <div style={{ fontSize: 12, color: 'var(--green)' }}>✓ All rows parsed successfully.</div>
              )}
              <button
                className="btn btn-ghost btn-sm"
                style={{ marginTop: 8 }}
                onClick={() => navigate(`/review?batch_id=${batch.id}`)}
              >
                View records from this batch →
              </button>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function Batches() {
  const { activeClient } = useAuth();
  const navigate = useNavigate();
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!activeClient) return;
    getBatches(activeClient.id).then(d => {
      setBatches(d.results || d);
    }).finally(() => setLoading(false));
  }, [activeClient]);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Ingestion Batches</h1>
          <div className="subtitle">Full history of every upload, with parse errors and row counts</div>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/upload')}>
          + New Upload
        </button>
      </div>
      <div className="page-body">
        {loading
          ? <div className="loading"><div className="spinner" /><span>Loading…</span></div>
          : batches.length === 0
            ? (
              <div className="empty-state">
                <Database size={48} />
                <h3>No batches yet</h3>
                <p>Upload a SAP export, utility CSV, or travel report to get started.</p>
                <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={() => navigate('/upload')}>Upload Data</button>
              </div>
            )
            : (
              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th style={{ width: 40 }}></th>
                      <th>Source</th>
                      <th>File</th>
                      <th>Uploaded</th>
                      <th>By</th>
                      <th>Period</th>
                      <th>Rows</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batches.map(b => <BatchRow key={b.id} batch={b} />)}
                  </tbody>
                </table>
              </div>
            )
        }
      </div>
    </>
  );
}
