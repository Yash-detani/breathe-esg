import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { uploadFile } from '../api';
import { useAuth } from '../AuthContext';
import { Upload as UploadIcon, FileText, AlertTriangle, CheckCircle } from 'lucide-react';

const SOURCE_META = {
  sap: {
    label: 'SAP Export',
    hint: 'MB51 goods receipts or ME2M purchase orders. CSV or tab-separated, German or English headers.',
    accept: '.csv,.txt,.tsv',
    example: 'MB51_fuel_goods_receipts_Q1_2024.csv',
    color: 'var(--green)',
  },
  utility: {
    label: 'Utility Portal Export',
    hint: 'Meter consumption CSV from MSEDCL, BESCOM, or similar portals. Includes meter ID, billing period, kWh.',
    accept: '.csv,.txt',
    example: 'MSEDCL_meter_consumption_Mar2024.csv',
    color: 'var(--blue)',
  },
  travel: {
    label: 'Corporate Travel Report',
    hint: 'Concur or Navan trip report export. Flights, hotels, car rentals. IATA codes used for distance calc.',
    accept: '.csv,.txt,.tsv',
    example: 'Navan_travel_report_Q1_2024.csv',
    color: '#d8b4fe',
  },
};

export default function Upload() {
  const { activeClient } = useAuth();
  const navigate = useNavigate();
  const fileRef = useRef();

  const [sourceType, setSourceType] = useState('sap');
  const [file, setFile]             = useState(null);
  const [dragOver, setDragOver]     = useState(false);
  const [loading, setLoading]       = useState(false);
  const [result, setResult]         = useState(null);
  const [error, setError]           = useState('');

  const handleFile = (f) => {
    if (f) { setFile(f); setResult(null); setError(''); }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  const handleSubmit = async () => {
    if (!file || !activeClient) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const fd = new FormData();
      fd.append('source_type', sourceType);
      fd.append('file', file);
      fd.append('client_id', activeClient.id);
      const batch = await uploadFile(fd);
      setResult(batch);
    } catch (err) {
      setError(err.response?.data?.error || err.response?.data?.file?.[0] || 'Upload failed. Check file format.');
    } finally {
      setLoading(false);
    }
  };

  const meta = SOURCE_META[sourceType];

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Upload Data</h1>
          <div className="subtitle">Ingest SAP exports, utility CSVs, or travel reports</div>
        </div>
      </div>
      <div className="page-body" style={{ maxWidth: 680 }}>

        {/* Source type selector */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 24 }}>
          {Object.entries(SOURCE_META).map(([key, m]) => (
            <button
              key={key}
              onClick={() => { setSourceType(key); setFile(null); setResult(null); setError(''); }}
              style={{
                padding: '14px 12px',
                border: `1px solid ${sourceType === key ? m.color : 'var(--border2)'}`,
                borderRadius: 6,
                background: sourceType === key ? `rgba(${key === 'sap' ? '74,222,128' : key === 'utility' ? '96,165,250' : '216,180,254'},0.06)` : 'var(--surface)',
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'all 0.12s',
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 600, color: sourceType === key ? m.color : 'var(--text)', marginBottom: 4 }}>
                {m.label}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.4 }}>{m.hint}</div>
            </button>
          ))}
        </div>

        {/* Drop zone */}
        <div
          className={`upload-zone${dragOver ? ' drag-over' : ''}`}
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current.click()}
        >
          <div className="upload-zone-icon"><UploadIcon size={36} /></div>
          <h3>Drop your {meta.label} here</h3>
          <p>or click to browse · {meta.accept}</p>
          {file && <div className="file-name">{file.name} ({(file.size / 1024).toFixed(1)} KB)</div>}
          <input
            ref={fileRef}
            type="file"
            accept={meta.accept}
            style={{ display: 'none' }}
            onChange={e => handleFile(e.target.files[0])}
          />
        </div>

        <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 8, fontFamily: 'var(--mono)' }}>
          Example filename: {meta.example}
        </div>

        {error && (
          <div style={{ marginTop: 14, padding: '10px 14px', background: 'var(--red-dim)', border: '1px solid rgba(248,113,113,0.2)', borderRadius: 4, fontSize: 13, color: 'var(--red)' }}>
            <AlertTriangle size={13} style={{ marginRight: 6 }} />{error}
          </div>
        )}

        <button
          className="btn btn-primary"
          style={{ marginTop: 16, width: '100%', justifyContent: 'center', padding: '11px' }}
          disabled={!file || loading}
          onClick={handleSubmit}
        >
          {loading ? <><div className="spinner" style={{ borderTopColor: '#0d0f12' }} /> Processing…</> : <><UploadIcon size={14} /> Ingest File</>}
        </button>

        {/* Result */}
        {result && (
          <div style={{ marginTop: 20, padding: 20, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}>
            <div className="gap-8" style={{ marginBottom: 12 }}>
              <CheckCircle size={16} color="var(--green)" />
              <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-head)' }}>Ingestion complete</span>
              <span className={`badge badge-${result.status === 'complete' ? 'approved' : result.status === 'partial' ? 'flagged' : 'rejected'}`}>
                {result.status_display}
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 16 }}>
              {[
                { label: 'Rows ingested', value: result.success_rows, color: 'var(--green)' },
                { label: 'Rows failed', value: result.failed_rows, color: result.failed_rows > 0 ? 'var(--red)' : 'var(--text-dim)' },
                { label: 'Rows flagged', value: result.flagged_rows, color: result.flagged_rows > 0 ? 'var(--amber)' : 'var(--text-dim)' },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ textAlign: 'center' }}>
                  <div style={{ fontFamily: 'var(--mono)', fontSize: 24, fontWeight: 500, color }}>{value}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>{label}</div>
                </div>
              ))}
            </div>
            {result.error_log?.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-dim)', marginBottom: 6 }}>
                  Parse errors
                </div>
                <div style={{ maxHeight: 120, overflowY: 'auto', fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--red)', background: 'var(--red-dim)', padding: '8px 10px', borderRadius: 4 }}>
                  {result.error_log.slice(0, 10).map((e, i) => (
                    <div key={i}>Row {e.row}: {e.message}</div>
                  ))}
                  {result.error_log.length > 10 && <div>…and {result.error_log.length - 10} more</div>}
                </div>
              </div>
            )}
            <div className="gap-8">
              <button className="btn btn-primary btn-sm" onClick={() => navigate('/review?review_status=pending')}>
                Go to Review Queue →
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/batches`)}>
                View batch details
              </button>
            </div>
          </div>
        )}

        {/* Format guide */}
        <div style={{ marginTop: 32 }}>
          <div style={{ fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-dim)', marginBottom: 10 }}>
            Expected format: {meta.label}
          </div>
          <FormatGuide source={sourceType} />
        </div>
      </div>
    </>
  );
}

function FormatGuide({ source }) {
  const guides = {
    sap: {
      cols: ['Belegnummer / Document Number', 'Belegdatum / Document Date', 'Werk / Plant', 'Kostenstelle / Cost Center', 'Materialbeschreibung / Material Description', 'Warengruppe / Material Group', 'Menge / Quantity', 'Einheit / Unit'],
      notes: ['German or English headers accepted', 'Dates: DD.MM.YYYY or YYYYMMDD', 'Numbers: European (1.234,56) or US (1,234.56)', 'Units: L, KG, M3, KWH, MWH, EUR, INR', 'Separator: tab, semicolon, or comma auto-detected'],
    },
    utility: {
      cols: ['Meter ID / MPAN / Account Number', 'From Date / Start Date', 'To Date / End Date', 'Consumption (kWh) / Units Consumed', 'Tariff Code / Rate', 'Location / Site Name'],
      notes: ['Billing periods need not align with calendar months', 'kWh, MWh, Units (India) all accepted', 'Green tariff keywords trigger Scope 2 market-based', 'Peak + off-peak columns summed if no total column'],
    },
    travel: {
      cols: ['Employee / Traveler', 'Report ID / Booking Ref', 'Trip Type (Flight/Hotel/Car/Rail)', 'Departure Date', 'From / Origin (IATA)', 'To / Destination (IATA)', 'Class of Service', 'Distance (km/miles, optional)'],
      notes: ['Flight distance auto-calculated from IATA codes if not given (haversine, flagged)', 'Hotel nights derived from check-in / check-out if nights not given', 'Car distance estimated at 50km/day if not provided (flagged)', 'DEFRA 2023 factors used, incl. radiative forcing for flights'],
    },
  };
  const g = guides[source];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, fontSize: 12 }}>
      <div>
        <div style={{ color: 'var(--text-dim)', marginBottom: 6, fontSize: 11 }}>Expected columns</div>
        {g.cols.map(c => (
          <div key={c} style={{ fontFamily: 'var(--mono)', color: 'var(--text)', padding: '3px 0', borderBottom: '1px solid var(--border)', fontSize: 11 }}>{c}</div>
        ))}
      </div>
      <div>
        <div style={{ color: 'var(--text-dim)', marginBottom: 6, fontSize: 11 }}>Notes</div>
        {g.notes.map(n => (
          <div key={n} style={{ color: 'var(--text)', padding: '3px 0', borderBottom: '1px solid var(--border)', fontSize: 11 }}>• {n}</div>
        ))}
      </div>
    </div>
  );
}
