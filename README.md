# Code-Mixed Lecture Notes Generator

A web application under staged development for turning classroom recordings containing English-Telugu code-mixed speech into transcripts and study materials. The planned outputs include structured English notes, concise Telugu-supported explanations, revision points, a basic MCQ quiz, and a downloadable PDF.

Phases 1-3 and Phases 6-10 application code, production preparation, security/quality audit, and documentation handoff are complete locally. Phase 4 transcription implementation and Phase 5 Gemini backend are complete with open external verification gates (no real English-Telugu recording evaluated on Groq yet; configured Gemini credential returned HTTP 401 during model check). All backend APIs, optional HTTP Basic Auth public access control, production startup configuration (`Procfile`, `Dockerfile`), Telugu-capable PDF export, and all 10 React frontend screens are implemented and locally tested. Live cloud deployment awaits operator hosting/MySQL accounts and provider validation.

## Project status

- Requirements and architecture are documented in this README, [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md), and [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md).
- Groq uses `whisper-large-v3-turbo`; provider behavior and persistence are covered with mocked tests, but no lecture audio has been sent to Groq. Code-mixed transcription quality has not been evaluated.
- Gemini uses the configured `gemini-3.5-flash-lite` model with structured output validation, source excerpts, persisted checkpoints, and isolated regeneration. The configured API key returned HTTP 401 from Google's model-list endpoint; live access remains unverified, and no lecture content has been sent to Gemini. Update `GEMINI_API_KEY` locally before live generation.
- Processing jobs use MySQL-backed leases, stale-job recovery, bounded retries, and manual retry limits. The separate worker handles transcription and all four Gemini generation stages.
- The project uses Python 3.12.10 in a fresh `.venv`; backend dependencies are installed and `pip check` passes.
- MySQL80 is running. Authenticated connectivity to `lecture_notes_db`, migration upgrade/downgrade, and Alembic schema checks have passed. The MySQL 8.0.46 client is installed outside PATH.
- FFmpeg is not installed or on PATH. It is not required by the current backend foundation.

## Planned stack

- Frontend: React, JavaScript, React Router, CSS.
- Backend: Python, FastAPI, Pydantic, SQLAlchemy.
- Database: MySQL.
- Speech recognition: Groq-hosted Whisper Large V3 Turbo, subject to current provider availability.
- Educational content generation: Google Gemini Flash, model selected by configuration.
- PDF: ReportLab with a verified Telugu-capable font.

The intended pipeline uses hosted inference only. English is the main language of the notes; Telugu supports selected concept explanations and is preserved in the transcript. No English-Telugu transcription quality claim has been made because no real lecture recording has been evaluated.

## Planned architecture

The React frontend communicates with a modular FastAPI backend through a centralized API layer (`frontend/src/api/lectures.js`) with workspace caching to avoid repeat fetches and repeat AI calls when reopening saved lectures. A separate worker claims MySQL-backed jobs using leases; audio and ReportLab/Noto Sans Telugu PDFs remain in configurable file storage. Transcripts, generated notes, Telugu explanations, revision points, quiz data, and PDFs are persisted before their stage checkpoints advance.

## Documentation

- [Design system (LUCENT)](./DESIGN_SYSTEM.md)
- [Groq and Gemini API setup](./API_SETUP_GUIDE.md)
- [Deployment planning and requirements](./DEPLOYMENT_GUIDE.md)

## Local backend setup

From the project root in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Set `DATABASE_URL` in the ignored `.env` to a valid local MySQL account before using the database health check or migrations. Do not paste credentials into source files or commit `.env`.

Run the API from the project root:

```powershell
python -m uvicorn backend.app.main:app --reload
```

The API liveness check is `/health`; `/health/database` requires a valid `DATABASE_URL`. Interactive API documentation is at `/docs`. CORS restricts cross-origin browser access to origins configured in `FRONTEND_URL`. The API supports upload/history/details, processing status/retry, saved transcripts, `GET /lectures/{lecture_id}/notes`, `/explanations`, `/revision-points`, `/quiz`, and `/pdf`, `POST /lectures/{lecture_id}/quiz/submit`, and `POST /lectures/{lecture_id}/regenerate/{feature}` (`notes`, `explanations`, `revision-points`, or `quiz`).

Run the separately managed worker in another PowerShell terminal:

```powershell
python -m backend.app.workers.run
```

The worker requires `GROQ_API_KEY` and `GEMINI_API_KEY`, resumes saved jobs from their last successful stage, validates audio before the Groq request, and stores each output before checkpointing success. API and worker must use the same MySQL database and audio storage. See [API_SETUP_GUIDE.md](./API_SETUP_GUIDE.md) for provider setup, including the pending Gemini key correction and real-recording evaluation gate.

After configuring a working MySQL account in `.env`, apply the schema migrations:

```powershell
python -m alembic upgrade head
```

Start the frontend in a second PowerShell terminal:

```powershell
Set-Location frontend
npm install
Copy-Item .env.example .env
npm run dev
```

In development, Vite proxies `/api` requests to `127.0.0.1:8000`. Configure `VITE_API_BASE_URL` when using a different API base URL. `VITE_MAX_UPLOAD_SIZE_BYTES` controls the frontend's early size check; backend validation is authoritative.

Run the backend and frontend checks with:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

The current verified backend suite reports 96 passing tests; the frontend suite reports 20 passing tests with 0 lint warnings/errors (`oxlint`) and a passing production build (`vite build`). Phase 6 MySQL migration `0cec2152fba2` is applied to MySQL and Alembic reports no schema drift; `pip check` passes. These local/mocked tests do not constitute live Gemini access, real-recording transcription-quality verification, or live public-cloud deployment.

```powershell
Set-Location frontend
npm test
npm run lint
npm run build
```

## Scope boundaries

The first release is limited to recorded MP3/WAV English-Telugu lectures. Live transcription, video, other language pairs, speaker identification, chatbot functionality, advanced quiz analytics, and complex account/role systems are out of scope.
