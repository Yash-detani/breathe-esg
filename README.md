# Breathe ESG — Emissions Ingestion Platform

A Django REST + React prototype for ingesting, normalising, and reviewing multi-source emissions data (SAP, utility portals, corporate travel) before audit sign-off.

**Live demo:** https://breathe-esg-frontend.onrender.com  
**Backend API:** https://breathe-esg-backend.onrender.com/api/  
**Admin panel:** https://breathe-esg-backend.onrender.com/admin/

| Credential | Username | Password |
|-----------|----------|----------|
| Admin     | `admin`  | `demo1234` |
| Analyst   | `analyst`| `demo1234` |

---

## What it does

- **Ingest** SAP MB51/ME2M flat file exports, utility portal CSVs, and Concur/Navan travel reports
- **Normalise** units (litres, kWh, km, kg, USD), dates (DD.MM.YYYY, YYYYMMDD, etc.), and number formats (European 1.234,56 and US 1,234.56)
- **Classify** every record into Scope 1 / 2 / 3 with GHG Protocol category
- **Calculate** CO₂e using DEFRA 2023 and IEA 2022 emission factors
- **Auto-flag** suspicious records (anomalous quantities, missing plant codes, estimated distances)
- **Surface** a review dashboard where analysts can approve, reject, or flag records individually or in bulk
- **Audit-trail** every action (who changed what, when, before/after diff)

---

## Local development setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Git

### Backend

```bash
git clone <your-repo-url>
cd breathe-esg/backend

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create .env (optional — SQLite used by default)
cp ../.env.example .env

python manage.py migrate
python manage.py seed_demo        # Creates demo client, users, and sample records
python manage.py runserver
```

Backend runs at http://localhost:8000

### Frontend

```bash
cd breathe-esg/frontend
npm install

# Point at local backend
echo "REACT_APP_API_URL=http://localhost:8000" > .env

npm start
```

Frontend runs at http://localhost:3000

### Demo credentials (local)
- `admin` / `demo1234`
- `analyst` / `demo1234`

### Try uploading sample files

The `sample_data/` directory has three realistic test files:

| File | Source type | What it tests |
|------|-------------|---------------|
| `SAP_MB51_fuel_Q1_2024.csv` | SAP | German headers, European numbers, missing plant code, N/A quantity row |
| `MSEDCL_utility_Q1_2024.csv` | Utility | Non-calendar billing periods, green tariff (market-based Scope 2), consumption spike |
| `Navan_travel_Q1_2024.csv` | Travel | IATA distance estimation, missing employee, unrecognised trip type (Ferry) |

---

## Deployment on Render (recommended)

1. Push this repo to GitHub (private is fine)
2. Go to https://render.com → New → Blueprint
3. Connect your repo — Render reads `render.yaml` automatically
4. It will create: a PostgreSQL database, a Python web service (Django), and a static site (React)
5. After deploy, run seed data via the Render Shell:
   ```bash
   cd backend && python manage.py seed_demo
   ```

**Environment variables set automatically by render.yaml:**
- `SECRET_KEY` — auto-generated
- `DATABASE_URL` — from the Postgres service
- `REACT_APP_API_URL` — from the backend service host

**CORS:** `CORS_ALLOW_ALL_ORIGINS = True` in settings for prototype simplicity. Lock this to the frontend domain in production.

---

## Deployment on Railway

```bash
# Install Railway CLI
npm i -g @railway/cli
railway login
railway init

# Add PostgreSQL plugin in Railway dashboard, then:
railway up
railway run python backend/manage.py migrate
railway run python backend/manage.py seed_demo
```

Set env vars in Railway dashboard:
- `SECRET_KEY`
- `DEBUG=False`
- `DATABASE_URL` (auto-set by Railway Postgres plugin)

---

## API overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/token/` | POST | Get JWT tokens (username, password) |
| `/api/auth/token/refresh/` | POST | Refresh access token |
| `/api/me/` | GET | Current user + client memberships |
| `/api/clients/` | GET | Clients the user belongs to |
| `/api/upload/` | POST | Upload a data file (multipart) |
| `/api/batches/` | GET | Ingestion batch history |
| `/api/batches/{id}/failed_rows/` | GET | Failed parse rows for a batch |
| `/api/records/` | GET | Emission records (filterable) |
| `/api/records/{id}/` | GET | Single record with audit trail |
| `/api/records/{id}/review/` | PATCH | Single record review action |
| `/api/records/bulk_review/` | POST | Bulk approve/flag/reject |
| `/api/dashboard/` | GET | Aggregated stats for dashboard |

**Filter parameters for `/api/records/`:**
`client_id`, `scope`, `source_type`, `review_status`, `is_flagged`, `batch_id`, `reporting_year`, `search`, `page`

---

## Project structure

```
breathe-esg/
├── backend/
│   ├── breathe_esg/          Django project (settings, urls, wsgi)
│   ├── ingestion/
│   │   ├── models.py         Core data model (see MODEL.md)
│   │   ├── parsers/
│   │   │   ├── sap_parser.py     SAP ALV flat file parser
│   │   │   ├── utility_parser.py Utility portal CSV parser
│   │   │   └── travel_parser.py  Concur/Navan travel report parser
│   │   ├── services.py       Ingestion orchestration + emission factor lookup
│   │   ├── views.py          REST API views
│   │   ├── serializers.py    DRF serializers
│   │   └── management/commands/seed_demo.py  Demo data
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.jsx     Stats, charts, recent batches
│       │   ├── ReviewQueue.jsx   Main analyst workflow table
│       │   ├── RecordDetail.jsx  Single record + audit trail + review panel
│       │   ├── Upload.jsx        File upload with format guide
│       │   └── Batches.jsx       Ingestion history + failed row inspection
│       ├── api.js                Axios client with JWT handling
│       └── AuthContext.js        Auth state + client switching
├── docs/
│   ├── MODEL.md      Data model rationale
│   ├── DECISIONS.md  Every ambiguity resolved
│   ├── TRADEOFFS.md  Three deliberate omissions
│   └── SOURCES.md    Research on each data source
├── sample_data/      Test files for each source type
├── render.yaml       Render Blueprint deployment config
└── Procfile          Railway/Heroku deployment
```

---

## Documentation

- [`docs/MODEL.md`](docs/MODEL.md) — Full data model with design rationale
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — Every ambiguity resolved + PM questions
- [`docs/TRADEOFFS.md`](docs/TRADEOFFS.md) — Three deliberate omissions and why
- [`docs/SOURCES.md`](docs/SOURCES.md) — Research on each data source
