# API Setup Guide

## Status

The upload, lecture-record, background-job, Groq transcription, transcript retrieval, Gemini study-material APIs, Telugu-capable PDF export, CORS origin enforcement (`FRONTEND_URL`), and complete 10-screen React frontend are implemented and locally tested. Groq behavior is covered by mocked provider and worker tests; no lecture audio has been sent to Groq, so English-Telugu recognition quality remains unevaluated. Gemini generation is covered by mocked provider and persistence tests, but live credential access remains unverified because Google's model-list endpoint returned HTTP 401 for the configured key. No lecture content has been sent to Gemini.

The backend will use:

- Groq for hosted speech recognition.
- Google Gemini for educational content generation.

Never put provider credentials in React, source code, logs, or committed files.

## Local backend and MySQL setup

The backend foundation uses Python 3.12 and SQLAlchemy with the `mysql+pymysql` driver.

1. Create a fresh environment and install development dependencies:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements-dev.txt
   ```

2. Copy `.env.example` to `.env`.
3. If needed, use an authorized MySQL administrator account (for example through MySQL Workbench) to create a schema and a dedicated local development account. Replace the sample password locally:

   ```sql
   CREATE DATABASE lecture_notes_db
       CHARACTER SET utf8mb4
       COLLATE utf8mb4_0900_ai_ci;

   CREATE USER 'lecture_notes_user'@'127.0.0.1'
       IDENTIFIED BY 'replace_with_a_local_secret';

   GRANT ALL PRIVILEGES ON lecture_notes_db.*
       TO 'lecture_notes_user'@'127.0.0.1';
   ```

4. Configure `DATABASE_URL` in the ignored `.env` for that account. URL-encode special characters in the password. Do not commit or paste the password into source code or chat.
5. Verify the connection with `python -m uvicorn backend.app.main:app --reload`, then request `/health/database`.
6. Apply schema migrations after the database connection has been verified.

The current environment has a running MySQL80 service and the MySQL 8.0.46 client at `C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe`. Authenticated SQLAlchemy connectivity to the `lecture_notes_db` schema was verified. The MySQL client is not on PATH. The upload API's MySQL persistence and retrieval were also smoke-tested using a temporary synthetic WAV; the test row and file were removed afterward.

Apply the current schema using Alembic from the project root:

```powershell
python -m alembic upgrade head
python -m alembic current
```

The initial, processing-job, transcript metadata, study-material, and Phase 6 `lecture_pdfs` migrations were applied to MySQL; Alembic reports revision `0cec2152fba2` as head and `alembic check` reports no model/schema differences. The backend's `/health` endpoint checks API liveness. `/health/database` returns a sanitized error when `DATABASE_URL` is absent, invalid, or the database cannot be reached.

FFmpeg was not found on PATH or the checked common installation locations. Current MP3/WAV validation uses Mutagen and does not require FFmpeg. Verify/install FFmpeg only if a later audio-processing step requires it.

## Upload API and audio limits

The backend accepts `POST /lectures` with a multipart `file` field, lists records through `GET /lectures?limit=20&offset=0`, and returns saved details through `GET /lectures/{lecture_id}`. Accepted formats are MP3 and WAV. The server validates media type and content, non-empty/readable audio, size, and duration. Files are stored under `UPLOAD_DIR`, not in MySQL; metadata and queued processing state are stored in the database.

Configure these backend settings in `.env`:

```dotenv
UPLOAD_DIR=uploads
MAX_UPLOAD_SIZE_BYTES=25000000
MAX_AUDIO_DURATION_SECONDS=3600
GROQ_MAX_AUDIO_SIZE_BYTES=25000000
```

The effective upload byte limit is the lower of `MAX_UPLOAD_SIZE_BYTES` and `GROQ_MAX_AUDIO_SIZE_BYTES`. The 25,000,000-byte default is a conservative configured limit based on provider documentation checked during implementation; confirm the applicable account/model restrictions before changing it. No audio has yet been sent to Groq. The frontend can use `VITE_MAX_UPLOAD_SIZE_BYTES` for early feedback, but backend validation is authoritative.

The frontend uses `VITE_API_BASE_URL` (default `/api`). Vite's local development proxy forwards `/api` to `http://127.0.0.1:8000`; production must configure an appropriate API base URL rather than rely on the development proxy.

To configure the frontend locally, copy `frontend/.env.example` to `frontend/.env` and adjust values if needed. Frontend variables are public build-time configuration; never put provider or database secrets in them.

## Background worker and job status

Start the worker from the project root in a separate PowerShell terminal after applying migrations:

```powershell
python -m backend.app.workers.run
```

The API and worker must use the same `DATABASE_URL` and `UPLOAD_DIR`. `GET /lectures/{lecture_id}/processing` returns job status, stage checkpoints, retry information, and a safe error message. `POST /lectures/{lecture_id}/retry` retries a failed job, subject to the configured manual retry cap.

Jobs are claimed with MySQL row locks and `SKIP LOCKED`, protected by renewable leases, recovered when a lease expires, and retried with bounded exponential backoff. Stage attempts and the last successful stage are persisted. The worker resumes jobs from their saved stage, revalidates audio before sending it to Groq, and persists each output before checkpointing success. It requires both `GROQ_API_KEY` and `GEMINI_API_KEY`; configure the API and worker with the same database and audio storage.

Configure these job settings in `.env`:

```dotenv
PROCESSING_JOB_LEASE_SECONDS=300
PROCESSING_JOB_MAX_STAGE_ATTEMPTS=3
PROCESSING_JOB_MAX_MANUAL_RETRIES=2
PROCESSING_JOB_RETRY_BACKOFF_SECONDS=15
PROCESSING_JOB_POLL_INTERVAL_SECONDS=2
```

## Groq

1. Visit the [Groq developer console](https://console.groq.com/).
2. Create or select an account/project and create an API key using the current console workflow.
3. Review the current [Groq speech-to-text documentation](https://console.groq.com/docs/speech-to-text), including supported models, audio limits, and rate limits.
4. Put the key in the backend environment as `GROQ_API_KEY`.
5. Set `GROQ_MODEL` to the intended hosted model. The initial planned value is `whisper-large-v3-turbo`; verify availability before use.
6. Configure `GROQ_TIMEOUT_SECONDS` and provider-specific upload limits only after checking current documentation.
7. Start the API and separate worker. The worker requests `verbose_json` with segment timestamps and does not force a language hint, allowing code-mixed audio to be handled by the provider.
8. Inspect saved text at `GET /lectures/{lecture_id}/transcript` or in the lecture details UI.

The provider SDK's automatic retries are disabled; the job manager applies bounded retries. A persisted transcript is reused after a worker restart, but a crash after a successful Groq response and before transcript persistence can still cause the request to be repeated because provider idempotency is not available in this integration. Do not force English-only or Telugu-only transcription for mixed-language recordings without evaluation. Compare real English-Telugu lecture output with a manually corrected reference before reporting recognition quality. If quotas or rate limits are reached, retain the uploaded audio and job state, show a clear error, and allow a controlled retry after the limit permits. Do not rotate accounts to bypass quotas.

## Google Gemini

1. Visit [Google AI Studio](https://aistudio.google.com/) and create or select a project.
2. Create an API key in AI Studio and store it only in the backend `.env` as `GEMINI_API_KEY`. If a key has returned HTTP 401, replace it locally; never paste it into source code, logs, or chat.
3. Review Google's current [Gemini API documentation](https://ai.google.dev/gemini-api/docs), [Interactions API](https://aistudio.google.com/docs/interactions-overview), and [structured-output guide](https://aistudio.google.com/docs/structured-output).
4. The implemented default is `gemini-3.5-flash-lite`, selected after official documentation marked `gemini-2.5-flash` deprecated and recommended migration. The model documentation lists structured outputs as supported; actual API access depends on the configured key/project and was not verified because the configured key returned HTTP 401 during a model-list check.
5. The backend uses `google-genai` 3.6.1 and the Interactions API with a Pydantic JSON schema, `store=false`, an explicit timeout, and SDK retries disabled. The job manager applies bounded retries. It does not send audio to Gemini.
6. Structured responses are validated locally before persistence: excerpts must match the transcript, Telugu explanations must refer to a saved lecture concept and contain Telugu script, revision points are limited to 240 characters, and each quiz has five questions with four distinct options and one indexed correct answer.
7. Verify live access with a backend-only structured request after configuring a working key. Current mocked tests do not establish live API access or the accuracy of generated educational content.

Model names and quotas can change. Do not treat free access or quota as guaranteed. On quota, authentication, timeout, or malformed-response errors, preserve the transcript and any prior successful output; provider failures are reported through the job status endpoint.

Saved study-material APIs:

- `GET /lectures/{lecture_id}/notes`
- `GET /lectures/{lecture_id}/explanations`
- `GET /lectures/{lecture_id}/revision-points`
- `GET /lectures/{lecture_id}/quiz` — omits correct positions and explanations.
- `POST /lectures/{lecture_id}/quiz/submit` — requires one answer per question and returns grading/review only after submission.
- `POST /lectures/{lecture_id}/regenerate/{feature}` where `feature` is `notes`, `explanations`, `revision-points`, or `quiz`.

## Environment variables

The eventual backend configuration is expected to include values similar to:

```dotenv
ENVIRONMENT=development
LOG_LEVEL=INFO

GROQ_API_KEY=replace_with_your_groq_api_key
GROQ_MODEL=whisper-large-v3-turbo
GROQ_TIMEOUT_SECONDS=180

GEMINI_API_KEY=replace_with_your_gemini_api_key
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_TIMEOUT_SECONDS=120

DATABASE_URL=mysql+pymysql://username:password@localhost:3306/lecture_notes_db

UPLOAD_DIR=uploads
PDF_DIR=generated_pdfs
FRONTEND_URL=http://localhost:5173

# Leave blank locally; set all three when deploying publicly behind HTTPS
REQUIRE_AUTH=false
AUTH_USERNAME=
AUTH_PASSWORD=
```

When `REQUIRE_AUTH=true` (or when both `AUTH_USERNAME` and `AUTH_PASSWORD` are set), all `/lectures*` endpoints enforce HTTP Basic Auth while `/health` and `/health/database` remain public. Setting `ENVIRONMENT=production` hides interactive `/docs`, `/redoc`, and `/openapi.json`. See [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) for hosting comparisons, production checklist, and shared-storage constraints.

These are examples, not a generated `.env` file. Add real values only to an ignored local environment file or a deployment secret manager. Do not commit credentials. Production frontend origins, database URL, storage configuration, and worker settings must be configured for the chosen host.

## Verification checklist

- [x] MySQL health, migrations, and actual API upload/detail/history persistence are verified.
- [x] Upload validation tests cover MP3/WAV, malformed/mismatched media, size/duration limits, duplicate filenames, storage cleanup, and DB failure cleanup.
- [x] Groq authentication and configured model availability were checked without exposing the key or sending audio.
- [x] MySQL atomic job claims, worker validation, and stale-lease recovery were exercised; all smoke-test rows and files were removed.
- [x] Groq provider request configuration, timeout/error mapping, transcript persistence/reuse, transcript API, and UI are covered by mocked tests.
- [x] Gemini structured output, provider errors, persisted checkpoints, and bounded retries are implemented and covered by mocked tests.
- [x] Provider failure paths preserve previous successful stage results and isolate regeneration.
- [x] PDF export with bundled Noto Sans Telugu, `uharfbuzz` OpenType shaping, and content-hash reuse is verified visually and by tests.
- [x] Full 10-screen React frontend, light/dark themes, quiz security, saved-output caching/reopening, and CORS origin restrictions (`FRONTEND_URL`) are implemented and verified locally.
- [ ] Live Gemini credential/model access is verified with a backend-only request; current configured key returned HTTP 401.
- [ ] Actual English-Telugu recordings are evaluated against manually corrected reference transcripts.
