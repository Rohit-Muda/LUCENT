# Deployment Guide

## Status

**Prepared and locally verified; not publicly deployed.**

Production configuration, HTTP Basic Authentication access control (`REQUIRE_AUTH`, `AUTH_USERNAME`, `AUTH_PASSWORD`), production CORS settings, process definitions (`Procfile`, `Dockerfile`), graceful worker shutdown (`SIGTERM`/`SIGINT`), MySQL pool recycling, and React session-credential handling are implemented and verified locally (`96` backend tests, `20` frontend tests, `oxlint`, `vite build`, `alembic check` on MySQL head `0cec2152fba2`, and live `uvicorn` production smoke checks).

Live cloud deployment has **not** been executed because no external hosting accounts, payment methods, or cloud MySQL credentials were provisioned, and two external provider gates remain open:
- Live Gemini credential access returned `HTTP 401` during the prior model-list check (`GEMINI_API_KEY` must be replaced with a valid key).
- No real English-Telugu classroom audio recording has been evaluated on Groq.

---

## Required Deployment Components

The application consists of five runtime components:

1. **React Frontend**: Static SPA built with Vite (`frontend/dist`) communicating via `VITE_API_BASE_URL`.
2. **FastAPI Backend**: Modular HTTP API (`uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers`).
3. **MySQL 8.0+ Database**: Relational storage for lectures, transcripts, study materials, PDF metadata, and leased `processing_jobs` (uses `SELECT ... FOR UPDATE SKIP LOCKED` via PyMySQL).
4. **Shared Persistent Storage**: Durable filesystem directories (`UPLOAD_DIR`, `PDF_DIR`) readable and writable by **both** the API and the worker.
5. **Background Worker**: Separate long-running process (`python -m backend.app.workers.run`) polling and executing transcription, Gemini generation, and PDF creation.

> [!IMPORTANT]
> **Shared storage architectural rule:** `LocalAudioStorage` and `LocalPdfStorage` operate against POSIX paths (`UPLOAD_DIR` and `PDF_DIR`). If the API and worker run on separate containers or nodes that do not mount the same shared filesystem/volume, the worker cannot read uploaded audio and the API cannot serve worker-generated PDFs.

---

## Hosting Research & Comparison (Evaluated 2026-11-26)

### 1. Frontend (Static React SPA)

| Provider | Free Tier | Build & Custom Origin | Fit for This App |
| :--- | :--- | :--- | :--- |
| **Vercel** | Hobby free tier for static SPAs | Native Vite build, `VITE_*` env vars, automatic HTTPS | **Strong** — zero server management |
| **Cloudflare Pages** | Free tier for static assets | Native Vite build, custom HTTPS origin, generous bandwidth | **Strong** — zero server management |
| **Netlify** | Free Starter tier (build-minute caps) | Native Vite build, `VITE_*` env vars | Good alternative |
| **Render Static Sites** | Free static hosting | Native Vite build | Good if backend is on Render |

### 2. Backend API + Background Worker + Shared Storage

| Provider | Free Tier Limits | Background Worker Support | Shared Persistent Disk Support |
| :--- | :--- | :--- | :--- |
| **Single Linux VPS / Cloud VM** (e.g., Oracle Cloud Always Free ARM VM, Hetzner, DigitalOcean) | Oracle Always Free compute available (strict signup verification); low-cost VPS ~$4–$6/mo | Native: run `uvicorn` and `python -m backend.app.workers.run` as separate `systemd` units or containers | **Native shared POSIX volume** (`UPLOAD_DIR` + `PDF_DIR`) accessible to both API and worker without S3 rewrites |
| **Render** | Web free tier sleeps after 15m; **no free persistent disk**; **no free worker tier** (worker starts at **$7/mo** Starter) | Paid Background Worker service ($7/mo+ for 0.5 CPU / 512 MB) | Disks ($0.25/GB/mo) attach to **only one service**; a separate worker cannot share a Render Disk with the web service |
| **Railway** | $1/mo recurring credit on Free plan after trial; free services sleep when idle | Supported (service without public domain; ~$5–$7/mo 24/7 usage-billed) | Volumes (~$0.15/GB/mo) attach to a single service container unless consolidated or replaced with S3 object storage |
| **Fly.io** | **No permanent free tier** for new accounts (pay-as-you-go) | Supported via separate Machine without ingress (~$2.20+/mo smallest spec) | Fly Volumes are pinned per-Machine, not shared across separate API and worker Machines without NFS or S3 |

### 3. MySQL Database

| Provider | Free / Low-Cost Status | MySQL 8 Compatibility & Notes |
| :--- | :--- | :--- |
| **Self-managed MySQL 8.0 on the same VPS** | Included on VPS ($0 extra) | Full MySQL 8.0 feature parity (`FOR UPDATE SKIP LOCKED`, `utf8mb4`); requires operator backups |
| **Oracle Cloud Always Free MySQL HeatWave** | Always Free standalone DB (up to 50 GB) | Native MySQL compatibility; strict account verification |
| **TiDB Cloud Serverless / Starter** | Free tier (5 GiB row-based OLTP storage) | MySQL wire-protocol compatible; verify `FOR UPDATE SKIP LOCKED` locking behavior under target load before switching from MySQL 8.0 |
| **Railway MySQL** | Usage-billed after $1/mo free credit (sleeps on free plan) | Standard single-node MySQL container |
| **Aiven / PlanetScale** | **MySQL free tiers retired** (Aiven retired MySQL Free Tier in Nov 2026; PlanetScale retired Hobby free tier) | Paid tiers only for MySQL |

### Recommended Deployment Architecture

1. **Frontend:** Deploy `frontend/` (`npm run build` -> `dist`) to **Cloudflare Pages** or **Vercel** (free tier, automatic HTTPS), setting `VITE_API_BASE_URL` to your HTTPS API origin (e.g., `https://api.yourdomain.edu`).
2. **Backend API + Worker + Shared Storage (+ Optional MySQL 8.0):** Deploy on a **single Linux VPS / Cloud VM** (using `systemd` or Docker) behind Caddy/Nginx TLS. This runs the API and worker as independent processes while both mount the exact same local persistent volume for `UPLOAD_DIR` and `PDF_DIR`, and connects cleanly to either local MySQL 8.0 or an external managed MySQL 8.0 instance.
   - *Future multi-host scaling note:* If moving API and worker onto separate PaaS containers (Render/Railway/Fly), implement S3-compatible adapters (e.g., Cloudflare R2 or Backblaze B2, both offering 10 GB free storage) behind the existing `AudioStorage` and `PdfStorage` protocols in `backend/app/services/`.

---

## Production Configuration & Environment Variables

### Backend & Worker (shared `.env` or secret manager)

Both the FastAPI API and the worker process (`python -m backend.app.workers.run`) MUST use identical database, storage, limit, and retry settings:

```dotenv
ENVIRONMENT=production
LOG_LEVEL=INFO

# MySQL 8.0+ over PyMySQL (add ?ssl_ca=/path/to/ca.pem if managed MySQL requires TLS)
DATABASE_URL=mysql+pymysql://user:url_encoded_password@db-host:3306/lecture_notes_db

# Persistent paths mounted on shared durable disk accessible to both API and worker
UPLOAD_DIR=/var/lib/lecture-notes/uploads
PDF_DIR=/var/lib/lecture-notes/generated_pdfs

# Exact frontend origin(s), comma-separated; wildcards (*) are ignored
FRONTEND_URL=https://notes.yourdomain.edu

# Public access control (REQUIRED before exposing publicly)
REQUIRE_AUTH=true
AUTH_USERNAME=replace_with_operator_username
AUTH_PASSWORD=replace_with_strong_password

# Audio validation limits
MAX_UPLOAD_SIZE_BYTES=25000000
MAX_AUDIO_DURATION_SECONDS=3600
GROQ_MAX_AUDIO_SIZE_BYTES=25000000

# Hosted AI providers (backend-only; never expose to frontend)
GROQ_API_KEY=replace_with_groq_key
GROQ_MODEL=whisper-large-v3-turbo
GROQ_TIMEOUT_SECONDS=180

GEMINI_API_KEY=replace_with_valid_gemini_key
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_TIMEOUT_SECONDS=120

# Worker leasing & bounded retries
PROCESSING_JOB_LEASE_SECONDS=300
PROCESSING_JOB_MAX_STAGE_ATTEMPTS=3
PROCESSING_JOB_MAX_MANUAL_RETRIES=2
PROCESSING_JOB_RETRY_BACKOFF_SECONDS=15
PROCESSING_JOB_POLL_INTERVAL_SECONDS=2
```

### Public Access Control Behavior

- When `REQUIRE_AUTH=false` and `AUTH_USERNAME` / `AUTH_PASSWORD` are unset, endpoints allow unauthenticated access for **local development only**.
- When `AUTH_USERNAME` and `AUTH_PASSWORD` are both set, all `/lectures*` routes (upload, history, lecture details, processing status, retry, regenerate, transcript, notes, explanations, revision points, quiz, quiz submission, and PDF download) enforce **HTTP Basic Authentication** using constant-time credential comparison and return `HTTP 401` + `WWW-Authenticate: Basic realm="Code-Mixed Lecture Notes"` on missing/invalid credentials.
- **Fail-closed safety:** If `REQUIRE_AUTH=true` without credentials, or only one of `AUTH_USERNAME`/`AUTH_PASSWORD` is provided, protected endpoints reject requests with `HTTP 503` (`auth_misconfigured`).
- **Health endpoints** (`/health` and `/health/database`) stay unauthenticated for load-balancer and platform readiness probes.
- When `ENVIRONMENT=production`, FastAPI disables `/docs`, `/redoc`, and `/openapi.json`.
- CORS restricts browser origins to `FRONTEND_URL`, permits the `Authorization` and `Content-Type` headers, and exposes `Content-Disposition` so cross-origin PDF downloads keep their filename.
- The React frontend handles `HTTP 401` automatically by displaying an access-control sign-in form and storing session-only `Authorization: Basic ...` headers in `sessionStorage` (cleared automatically on `401` or clicking **Sign out**). Always deploy behind HTTPS so Basic credentials are encrypted in transit.

### Frontend Build Variables

```dotenv
VITE_API_BASE_URL=https://api.yourdomain.edu
VITE_MAX_UPLOAD_SIZE_BYTES=25000000
```

Build static assets from `frontend/`:

```bash
cd frontend
npm ci
npm run build
```

Deploy `frontend/dist/` with SPA history fallback (rewriting unknown paths such as `/lectures/:id` to `/index.html`).

---

## Deployment & Verification Sequence

1. **Provision infrastructure & accounts (manual operator prerequisite):**
   - Create/verify valid Groq and Google Gemini API keys (`GEMINI_API_KEY` must pass live verification).
   - Provision MySQL 8.0+ database (`utf8mb4`) and shared persistent directories (`UPLOAD_DIR`, `PDF_DIR`).
2. **Install Python dependencies & apply Alembic migrations:**
   ```bash
   python -m pip install -r requirements.txt
   python -m alembic upgrade head
   python -m alembic check
   ```
3. **Start API and separate worker (or use `Procfile` / `Dockerfile`):**
   - API process: `uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers`
   - Worker process: `python -m backend.app.workers.run` (handles `SIGTERM`/`SIGINT` cleanly and disposes DB connections on exit)
4. **Verify deployed endpoints before opening access:**
   - `GET /health` -> `200 {"status": "ok"}`
   - `GET /health/database` -> `200 {"status": "ok", "database": "ok"}`
   - `GET /docs` -> `404` when `ENVIRONMENT=production`
   - `GET /lectures` without credentials -> `401`
   - `GET /lectures` with valid Basic credentials -> `200`
   - Upload a real test English-Telugu MP3/WAV, wait for completion across all stages (`validate_upload` -> `transcribe` -> `generate_notes` -> `generate_explanations` -> `generate_revision_points` -> `generate_quiz` -> `generate_pdf`), restart both API and worker processes, and confirm the saved lecture, generated outputs, and downloaded PDF remain accessible without repeating AI calls.
5. **Operations & backups:**
   - Back up the MySQL database (`mysqldump` / automated snapshots) and the `UPLOAD_DIR` / `PDF_DIR` storage volume on the same schedule so database `storage_key` references stay aligned with stored files.
