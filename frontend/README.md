# ForgeMind AI: Industrial Maintenance Copilot

**Ask your machine manuals a question. Get an answer with the document and page it came from.**

ForgeMind AI helps a factory maintenance team find answers in equipment manuals, SOPs and maintenance records. Upload PDFs, and the app indexes them, registers the machines it finds, and answers questions in plain language. Every answer is grounded in the uploaded documents and lists its sources. Dashboards for equipment, work orders and downtime are built only from the data you upload or import, never from fixed demo values.

> **Live demo:** _add your link here after deployment_

<!-- Add screenshots to docs/screenshots/ and uncomment:
![Dashboard](docs/screenshots/dashboard.png)
![Chat with sources](docs/screenshots/chat.png)
-->

## Features

- **Document chat (RAG):** questions are answered only from the uploaded documents, with source name, page and excerpt. If the documents do not contain the answer, the assistant says what is missing instead of guessing.
- **Troubleshooting assistant:** describe a fault and get likely causes, checks and fixes from the manuals, plus similar past work orders.
- **Automatic equipment registry:** upload a manual and its machine is added to Equipment. Equipment and work orders can also be added by hand or imported from CSV or JSON.
- **Maintenance work orders:** create, filter, search and update status; downtime is tracked per machine.
- **Live dashboard and analytics:** open work orders, downtime hours, work orders by status and priority, passages per document. All numbers and charts come from your data; with no data, the pages show clear empty states.
- **User accounts with roles:** sign-in with email and password; **admin** and **technician** roles with server-enforced permissions (see below).
- **Search:** BM25 keyword search by default, optional semantic search (Sentence Transformers and FAISS).
- **Friendly assistant:** greetings such as "hi" get an introduction and a few example questions.
- **Works on a phone and a laptop** from one address (same Wi-Fi), or online with HTTPS.

## Roles

| Action | Admin | Technician |
|---|:---:|:---:|
| View dashboard, equipment, work orders, documents, analytics | yes | yes |
| Chat and troubleshooting | yes | yes |
| Create and update work orders | yes | yes |
| Change a machine's status | yes | yes |
| Edit machine details, add or delete machines | yes | no |
| Delete work orders, import CSV or JSON | yes | no |
| Upload, re-index or delete documents | yes | no |
| Add, edit, switch off or delete users | yes | no |
| Change own password | yes | yes |

The first administrator is created from `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env` the first time the backend starts with an empty database. After that, users are managed on the **Users** page. An administrator cannot remove their own access, and the last active administrator is always protected.

## Tech stack

| Part | Technology |
|---|---|
| Backend | Python 3.12+, FastAPI, SQLAlchemy, SQLite, pydantic-settings |
| Retrieval | PDF text extraction (pypdf), chunking, BM25; optional Sentence Transformers + FAISS |
| Generation | Google Gemini (answers restricted to retrieved passages) |
| Auth | scrypt password hashes, HMAC-signed HttpOnly session cookie, login throttling (standard library only) |
| Frontend | Next.js 15, React 19, TypeScript |
| Deployment | Docker, Docker Compose, Caddy (automatic HTTPS) |
| Tests | pytest (about 400 tests), TypeScript type-check, Playwright checks |

## How it works

```
Upload PDF -> extract text -> split into passages -> index (BM25)  -> register the machine
Question   -> find the best passages -> Gemini answers using ONLY those passages -> answer + sources
```

## Quick start on Windows (no coding)

1. Install **Python 3.12+** and **Node.js 20+**.
2. Open PowerShell in the project folder and create the environment once:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r backend\requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in:
   ```
   GEMINI_API_KEY=your key from https://aistudio.google.com/apikey
   ADMIN_EMAIL=you@example.com
   ADMIN_PASSWORD=at least 8 characters
   ```
4. Double-click **`start_forgemind.bat`**. It starts the backend and the website and shows the address.
5. Open `http://localhost:3000` and sign in with the admin email and password. To use it from a phone on the same Wi-Fi, run `allow_phone_access.bat` once as Administrator and open the address shown by the launcher.

Without a Gemini key the app still works: the chat then returns the best matching excerpts from your documents.

### Run it manually

```bash
# backend (from the project root)
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
cp .env.example .env
uvicorn backend.app.main:app --reload --port 8000      # API docs: http://localhost:8000/docs

# frontend (second terminal)
cd frontend && npm install && npm run dev              # http://localhost:3000
```

The website forwards `/api` to the backend, so the browser only ever talks to one address.

## Try it with sample data

`data/sample/` contains sample manuals and CSV files (equipment and work orders). Sign in as admin, open **Upload** and add the PDFs, then use **Import CSV** on the Equipment and Maintenance pages. The dashboard, analytics and chat fill in from them. Try asking:

- "What causes low oil pressure on the compressor?"
- "How often should the pump seal be replaced?"

## Main API endpoints

All endpoints except health and login need a signed-in user. Interactive docs are at `/docs` (hidden when `APP_ENV=production`).

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | /api/auth/login, /api/auth/logout | everyone | Sign in and out |
| GET | /api/auth/me | signed in | Current user and role |
| POST | /api/auth/change-password | signed in | Change own password |
| GET, POST, PATCH, DELETE | /api/users | admin | Manage accounts |
| POST | /api/ask | signed in | Ask a question and get an answer with sources |
| POST | /api/troubleshoot | signed in | Diagnose a fault from the manuals |
| GET | /api/equipment, /api/maintenance | signed in | Registry and work orders |
| POST, DELETE | /api/equipment | admin | Add or delete machines |
| PATCH | /api/equipment/{id} | signed in | Technicians: status only |
| POST, PATCH | /api/maintenance | signed in | Create and update work orders |
| POST | /api/import/equipment, /api/import/work-orders | admin | CSV or JSON import |
| POST, DELETE | /api/documents/upload, /api/documents/{id} | admin | Upload, delete documents |
| GET | /api/documents, /api/analytics/summary | signed in | Documents and live statistics |
| GET | /api/health | public | Health check |

## Project structure

```
forgemind-ai/
├── backend/
│   └── app/
│       ├── api/            routes: auth, users, ask, documents, registry, imports, analytics, ...
│       ├── core/           settings, security (passwords, sessions, roles), logging
│       ├── generation/     Gemini client (grounded answers)
│       ├── ingestion/      PDF loading and chunking
│       ├── retrieval/      BM25 and optional semantic search
│       ├── models/         database tables (equipment, work orders, documents, users)
│       ├── services/       equipment naming, small talk
│       └── tests/          automated tests
├── frontend/
│   └── src/
│       ├── app/            pages: dashboard, chat, equipment, maintenance, analytics, documents, upload, users, account, login
│       ├── components/     shared UI (sidebar, forms, drawers, charts)
│       └── lib/            API client, auth, session, helpers
├── data/sample/            sample manuals and CSV files
├── evaluation/             retrieval benchmark questions
├── docker-compose.yml      local Docker run
├── docker-compose.prod.yml public server with automatic HTTPS (Caddy)
├── Caddyfile
├── .env.example            settings template for development
└── .env.production.example settings template for a server
```

## Configuration

Settings are read from `.env` (never commit this file).

| Setting | Purpose |
|---|---|
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini access |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | First administrator, created when there are no users |
| `SESSION_SECRET` | Signs the login cookie (required in production) |
| `AUTH_ENABLED` | `false` switches sign-in off for a private demo (everyone is an admin) |
| `LOGIN_ON_START` | `true` shows the login page after every backend restart |
| `SEED_SAMPLE_DATA` | `false` by default: pages show only your own data |
| `AUTO_REGISTER_EQUIPMENT` | Add a machine automatically when a manual is uploaded |
| `ENABLE_SEMANTIC_SEARCH` | Optional embeddings search |
| `MAX_UPLOAD_MB` | Upload limit (default 25) |

In production (`APP_ENV=production`) the app refuses to start without a private admin password of at least 12 characters and a random session secret of at least 32 characters.

## Security

- Passwords are stored as salted scrypt hashes; plain passwords are never stored or logged.
- The session cookie is HttpOnly, SameSite and Secure in production.
- Failed sign-ins are rate limited.
- Roles are enforced on the server for every request; the interface only hides what a user cannot do.
- Uploaded text is treated as data, so instructions inside a PDF cannot steer the model.
- `.env` is excluded from Git.

## Tests

```bash
pytest                                  # backend, about 400 tests
cd frontend && npx tsc --noEmit         # TypeScript check
```

## Deploy online

`docker-compose.prod.yml` runs the backend, the website and Caddy (automatic HTTPS) on a small Linux server. Copy `.env.production.example` to `.env`, fill it in, then:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

## Known limits

- One plant per installation; no multi-tenant support.
- Equipment names come from the uploaded file names.
- The chat answers from uploaded documents only and does not keep a conversation memory yet.
- The Docker deployment has not been load tested.

## Roadmap

Conversation memory, multiple plants, audit log of changes, scheduled preventive-maintenance reminders, and a CI pipeline.

## Author

Built by **Ebin Babu** ([@Ebin2111](https://github.com/Ebin2111)).
