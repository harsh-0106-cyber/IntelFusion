# TruSINT

**TruSINT is a public-data OSINT platform for discovering and organizing a
person's publicly visible digital footprint.** It combines live web search,
public social and academic sources, email intelligence, discussion discovery,
and locally indexed visual matching in one Flask application.

> **Use responsibly:** TruSINT is intended for education, journalism,
> cybersecurity research, and legitimate investigations. It must not be used
> for harassment, stalking, unauthorized profiling, or harm. The application
> is designed to use publicly available information and does not bypass login
> controls or access private data.

## What it provides

- **OSINT Search:** streams web, social, academic, discussion, and image
  findings as they arrive.
- **Account linking:** derives likely usernames and checks public profile URLs
  across professional, social, developer, identity, and research platforms.
- **Entity resolution:** deduplicates URLs, categorizes sources, builds a
  TF-IDF-style tag cloud, and flags possible homonyms.
- **PeopleRank:** calculates a transparent 0–100 visibility score from result
  volume, domain diversity, social coverage, authority sources, images, and
  keyword relevance.
- **LookMeUp:** analyzes public email-related signals such as name patterns,
  provider/MX data, Gravatar, breach responses, GitHub, public web mentions,
  Reddit, WHOIS-related data, photos, and username candidates.
- **ZLens:** validates images, strips EXIF metadata, computes SHA-256/dHash/
  aHash/pHash signatures, indexes permitted local datasets in SQLite, and
  retrieves exact or perceptual near-duplicate matches.
- **Exports:** supports JSON export and printable intelligence reports from the
  browser interface.

## Architecture

```text
Browser SPA
    │
    ├── GET /api/search          ── SSE people-search pipeline
    ├── GET /api/email-lookup    ── SSE email-intelligence pipeline
    └── /api/zlens/*             ── image ingestion, indexing, and retrieval
             │
             ├── Flask application (backend/app.py)
             ├── OSINT source adapters (backend/osint/)
             └── ZLens services + SQLite (backend/zlens/)
```

The frontend is framework-free HTML, CSS, and JavaScript. The backend uses
Flask, Requests, BeautifulSoup, Pillow, NumPy, and SQLite. No frontend build
step is required.

## Repository layout

```text
TruSINT/
├── backend/
│   ├── app.py                 # Flask routes, SSE orchestration, static serving
│   ├── osint/                 # Web, social, email, research, and ranking logic
│   ├── zlens/                 # Image preprocessing, indexing, and retrieval
│   ├── data/                  # Local collections, permitted dataset, uploads
│   ├── tests/                 # API, hashing, indexing, and retrieval tests
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── css/
│   └── js/
├── run.ps1                    # Windows one-click launcher
└── TECHNICAL_REPORT.md        # Detailed implementation report
```

## Quick start

### Requirements

- Python 3.10+ (Python 3.11+ recommended)
- Windows, macOS, or Linux
- Network access for live public-source lookups

### Windows PowerShell

```powershell
cd TruSINT
.\run.ps1
```

### Manual launch

```bash
cd TruSINT/backend
python -m venv .venv
# Activate .venv using the command for your shell
pip install -r requirements.txt
python app.py
```

Open <http://localhost:5000>.

## Optional configuration

Create `TruSINT/backend/.env` when optional integrations are needed:

```env
FLASK_PORT=5000
REQUEST_TIMEOUT=12
MAX_RESULTS_PER_SOURCE=10
GOOGLE_API_KEY=
GOOGLE_CSE_ID=
LENSO_API_KEY=
ZLENS_DB_PATH=
ZLENS_PERMITTED_DATASET_DIR=
```

DuckDuckGo-backed search works without API keys. Google Custom Search and
Lenso.ai are optional enhancements.

## Important API routes

| Route | Purpose |
|---|---|
| `GET /api/search?q=...` | SSE people and web OSINT search |
| `GET /api/email-lookup?email=...` | SSE email intelligence |
| `GET /api/health` | Application health and feature status |
| `POST /api/zlens/upload` | Validate and ingest an image |
| `POST /api/zlens/search` | Search local/live visual candidates |
| `POST /api/zlens/index/import` | Import a permitted image dataset |
| `GET /api/zlens/index/stats` | View indexed asset statistics |
| `GET /api/zlens/index/assets` | List indexed assets and provenance |

## Testing

From `TruSINT/backend`:

```bash
pytest -q
```

Most ZLens tests use synthetic images and temporary SQLite databases. Live
provider integrations may be affected by network availability, rate limits,
and upstream API or HTML changes.

## Security and privacy notes

ZLens validates image magic bytes, rejects malformed files, limits file size
and pixel count, normalizes orientation, strips EXIF metadata, and restricts
local dataset access to permitted directories. Visual matches are returned
only when supported by measured hashes or image comparisons; the system does
not fabricate similarity results.

Before production deployment, add authentication and authorization, restrict
CORS origins, add rate limiting and audit logging, use a production WSGI
server, and define retention rules for uploads, logs, databases, and exports.

## Documentation

See the [technical report](TECHNICAL_REPORT.md) for the full architecture,
pipeline behavior, API inventory, algorithms, configuration, testing, and
production recommendations.