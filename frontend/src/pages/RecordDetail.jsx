import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getRecord, reviewRecord } from '../api';
import { ArrowLeft, CheckCircle, XCircle, AlertTriangle, Clock } from 'lucide-react';

function DetailItem({ label, value, mono }) {
  return (
    <div className="detail-item">
      <label>{label}</label>
      <div className={`value${mono ? ' mono' : ''}${!value ? ' empty' : ''}`}>
        {value || '—'}
      </div>
    </div>
  );
}

function AuditEntry({ entry }) {
  return (
    <div className="audit-entry">
      <div className={`audit-dot ${entry.action}`} />
      <div>
        <div>
          <span className="audit-action">{entry.action_display}</span>
          <span className="audit-meta"> by {entry.actor?.username || 'system'} · {new Date(entry.timestamp).toLocaleString()}</span>
        </div>
        {entry.note && <div className="audit-note">"{entry.note}"</div>}
        {entry.diff && Object.keys(entry.diff).length > 0 && (
          <div style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--mono)', marginTop: 2 }}>
            {Object.entries(entry.diff).map(([k, v]) => (
              <span key={k}>{k}: {JSON.stringify(v.before)} → {JSON.stringify(v.after)} </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function RecordDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [record, setRecord]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [note, setNote]       = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [actionDone, setActionDone] = useState('');

  useEffect(() => {
    setLoading(true);
    getRecord(id).then(setRecord).finally(() => setLoading(false));
  }, [id]);

  const doAction = async (action) => {
    setActionLoading(true);
    try {
      const updated = await reviewRecord(id, action, note);
      setRecord(updated);
      setActionDone(action);
      setNote('');
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) return <div className="loading"><div className="spinner" /><span>Loading record…</span></div>;
  if (!record) return <div className="loading">Record not found.</div>;

  const r = record;
  const statusColor = {
    pending: 'var(--text-dim)', flagged: 'var(--amber)',
    approved: 'var(--green)', rejected: 'var(--red)'
  }[r.review_status] || 'var(--text-dim)';

  return (
    <>
      <div className="page-header">
        <div>
          <div className="gap-8" style={{ marginBottom: 6 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate(-1)}>
              <ArrowLeft size={13} /> Back
            </button>
            <span className="text-mono text-dim" style={{ fontSize: 12 }}>{r.id}</span>
          </div>
          <h1>
            {r.activity_type_display}
            <span style={{ marginLeft: 12, color: statusColor, fontSize: 14, fontWeight: 400 }}>
              [{r.review_status_display}]
            </span>
          </h1>
          <div className="subtitle">
            {r.source_type?.toUpperCase()} · {r.scope_display} · {r.activity_date}
          </div>
        </div>
      </div>

      <div className="page-body">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20 }}>
          {/* Main details */}
          <div>
            {/* Emissions */}
            <div className="detail-section">
              <div className="detail-section-title">Emissions</div>
              <div className="detail-grid">
                <DetailItem label="CO₂e" value={r.co2e_kg != null ? `${parseFloat(r.co2e_kg).toFixed(3)} kg (${(parseFloat(r.co2e_kg)/1000).toFixed(4)} t)` : 'Not calculated'} mono />
                <DetailItem label="Scope" value={r.scope_display} />
                <DetailItem label="Activity Type" value={r.activity_type_display} />
                {r.scope3_category && <DetailItem label="Scope 3 Category" value={r.scope3_category} />}
              </div>
              {r.emission_factor && (
                <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-dim)', fontFamily: 'var(--mono)' }}>
                  Factor: {r.emission_factor.factor_kg_co2e_per_unit} kgCO₂e/{r.emission_factor.unit}
                  · {r.emission_factor.source.toUpperCase()} {r.emission_factor.year}
                </div>
              )}
            </div>

            {/* Activity Data */}
            <div className="detail-section">
              <div className="detail-section-title">Activity Data</div>
              <div className="detail-grid">
                <DetailItem label="Raw Value" value={`${r.raw_value} ${r.raw_unit}`} mono />
                <DetailItem label="Canonical Value" value={`${r.canonical_value} ${r.canonical_unit}`} mono />
                <DetailItem label="Activity Date" value={r.activity_date} mono />
                {r.period_end && <DetailItem label="Period End" value={r.period_end} mono />}
                <DetailItem label="Reporting Year" value={r.reporting_year} />
              </div>
            </div>

            {/* Location / Source */}
            <div className="detail-section">
              <div className="detail-section-title">Location & Source</div>
              <div className="detail-grid">
                <DetailItem label="Location" value={r.location_name} />
                <DetailItem label="Country" value={r.country} />
                {r.meter_id && <DetailItem label="Meter ID" value={r.meter_id} mono />}
                {r.tariff_code && <DetailItem label="Tariff Code" value={r.tariff_code} mono />}
                {r.sap_document_number && <DetailItem label="SAP Doc#" value={r.sap_document_number} mono />}
                {r.sap_cost_center && <DetailItem label="Cost Centre" value={r.sap_cost_center} mono />}
                {r.sap_material_group && <DetailItem label="Material Group" value={r.sap_material_group} mono />}
              </div>
            </div>

            {/* Travel-specific */}
            {r.source_type === 'travel' && (
              <div className="detail-section">
                <div className="detail-section-title">Travel Details</div>
                <div className="detail-grid">
                  <DetailItem label="Traveler" value={r.traveler_name} />
                  <DetailItem label="Route" value={[r.travel_origin, r.travel_destination].filter(Boolean).join(' → ') || undefined} mono />
                  <DetailItem label="Class" value={r.travel_class} />
                  {r.distance_km && <DetailItem label="Distance" value={`${parseFloat(r.distance_km).toFixed(1)} km`} mono />}
                </div>
              </div>
            )}

            {/* Provenance */}
            <div className="detail-section">
              <div className="detail-section-title">Provenance</div>
              <div className="detail-grid">
                <DetailItem label="Source Row ID" value={r.source_row_id} mono />
                <DetailItem label="Batch File" value={r.batch_filename} />
                <DetailItem label="Ingested At" value={new Date(r.created_at).toLocaleString()} />
              </div>
            </div>

            {/* Flags */}
            {r.is_flagged && r.flag_reasons?.length > 0 && (
              <div className="detail-section">
                <div className="detail-section-title">Auto-detected Flags</div>
                <div className="flag-list">
                  {r.flag_reasons.map((f, i) => (
                    <span key={i} className="flag-pill">{f}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Audit trail */}
            <div className="detail-section">
              <div className="detail-section-title">Audit Trail</div>
              {(r.audit_trail || []).length === 0
                ? <div className="text-dim" style={{ fontSize: 12 }}>No audit entries.</div>
                : (r.audit_trail || []).map(e => <AuditEntry key={e.id} entry={e} />)
              }
            </div>
          </div>

          {/* Review panel */}
          <div>
            <div className="card" style={{ position: 'sticky', top: 20 }}>
              <div style={{ fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-dim)', marginBottom: 12 }}>
                Review Decision
              </div>

              <div style={{ marginBottom: 12, padding: 10, background: 'var(--surface2)', borderRadius: 4 }}>
                <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 4 }}>Current status</div>
                <span className={`badge badge-${r.review_status}`}>{r.review_status_display}</span>
                {r.reviewed_by && (
                  <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>
                    by {r.reviewed_by.username} · {r.reviewed_at ? new Date(r.reviewed_at).toLocaleString() : ''}
                  </div>
                )}
                {r.review_note && (
                  <div style={{ fontSize: 12, color: 'var(--text)', marginTop: 4, fontStyle: 'italic' }}>
                    "{r.review_note}"
                  </div>
                )}
              </div>

              <div className="form-group">
                <label className="form-label">Note (optional)</label>
                <textarea
                  className="form-input"
                  rows={3}
                  value={note}
                  onChange={e => setNote(e.target.value)}
                  placeholder="Explain your decision…"
                  style={{ resize: 'vertical' }}
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <button
                  className="btn btn-approve"
                  style={{ justifyContent: 'center' }}
                  disabled={actionLoading || r.review_status === 'approved'}
                  onClick={() => doAction('approve')}
                >
                  <CheckCircle size={13} /> Approve
                </button>
                <button
                  className="btn btn-flag"
                  style={{ justifyContent: 'center' }}
                  disabled={actionLoading || r.review_status === 'flagged'}
                  onClick={() => doAction('flag')}
                >
                  <AlertTriangle size={13} /> Flag for Follow-up
                </button>
                <button
                  className="btn btn-reject"
                  style={{ justifyContent: 'center' }}
                  disabled={actionLoading || r.review_status === 'rejected'}
                  onClick={() => doAction('reject')}
                >
                  <XCircle size={13} /> Reject
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ justifyContent: 'center', marginTop: 4 }}
                  disabled={actionLoading || r.review_status === 'pending'}
                  onClick={() => doAction('pending')}
                >
                  <Clock size={13} /> Reset to Pending
                </button>
              </div>

              {actionDone && (
                <div style={{ marginTop: 12, fontSize: 12, color: 'var(--green)', textAlign: 'center' }}>
                  ✓ Marked as {actionDone}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
