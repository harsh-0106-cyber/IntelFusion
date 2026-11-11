# TruSINT Technical Report

## 1. Scope and source snapshot

This report describes the project as implemented on the `main` branch at commit
`c007cf5eb54c266b0d3c82be3e35687ad32db73b` (`Refactor: rename IntelFusion to
TruSINT with latest updates and ZLens module`).

TruSINT is a Flask-based open-source intelligence (OSINT) web application. It
searches public web sources, public social-platform endpoints, academic
repositories, public discussions, and image sources, then presents normalized
results through a browser dashboard. The repository also contains ZLens, a
local visual retrieval subsystem for exact and near-duplicate image matching.

The application is designed around publicly available data. It does not
implement authentication-wall bypassing, private-data access, facial
identification, or an unrestricted external image database.

## 2. Executive summary

The project is a single-process Python web application with a static frontend.
`TruSINT/backend/app.py` constructs the Flask application, initializes the
search services, exposes REST and Server-Sent Events (SSE) endpoints, and
serves `TruSINT/frontend/index.html`.

The principal capabilities are:

- Multi-query web search using DuckDuckGo HTML results, with optional Google
  Custom Search JSON API fallback.
- Public social-platform probing, including GitHub and Reddit APIs, Wikipedia,
  and site-targeted searches for additional platforms.
- Probable account discovery from derived usernames across approximately 30
  platform templates.
- Academic and research discovery through Semantic Scholar, arXiv, CrossRef,
  and ORCID.
- Public comments and discussion discovery through Reddit, Hacker News,
  DuckDuckGo, and forum-targeted searches.
- Image harvesting, entity normalization, deduplication, tag-cloud generation,
  homonym heuristics, and a weighted PeopleRank visibility score.
- Email intelligence through pattern analysis, DNS/MX provider detection,
  Gravatar, HIBP, GitHub, public web search, Reddit, WHOIS/RDAP-related
  lookups, and username generation.
- ZLens image ingestion, EXIF removal, SHA-256 and perceptual hashing,
  persistent SQLite indexing, local exact/near-duplicate search, and optional
  live candidate verification.

## 3. Repository structure

```text
TruSINT/
├── backend/
│   ├── app.py
│   ├── requirements.txt
│   ├── data/
│   │   ├── collection/
│   │   ├── permitted_dataset/
│   │   └── uploads/
│   ├── osint/
│   │   ├── account_linker.py
│   │   ├── comments_finder.py
│   │   ├── email_intel.py
│   │   ├── entity_resolver.py
│   │   ├── image_harvester.py
│   │   ├── people_rank.py
│   │   ├── query_parser.py
│   │   ├── research_finder.py
│   │   ├── search_engine.py
│   │   ├── social_prober.py
│   │   ├── visual_intel.py
│   │   └── zlens_engine.py
│   ├── zlens/
│   │   ├── database.py
│   │   ├── engine.py
│   │   ├── indexer.py
│   │   ├── lenso_client.py
│   │   ├── preprocessor.py
│   │   ├── retriever.py
│   │   └── web_search.py
│   └── tests/
├── frontend/
│   ├── index.html
│   ├── css/
│   └── js/
└── run.ps1
```

The root `README.md` is currently empty. The application-specific documentation
is in `TruSINT/README.md`.

## 4. System architecture

### 4.1 Runtime model

The backend runs Flask in one process. Service objects are created at module
load time and reused by request handlers. The frontend is a static single-page
application with no build system or JavaScript framework. Browser requests use
SSE for long-running people and email investigations and JSON for synchronous
image-index operations.

The default server port is `5000`; `FLASK_PORT` can override it. Development
debug mode is enabled when `FLASK_ENV=development`.

### 4.2 People-search pipeline

The primary search path is `GET /api/search?q=...`. It emits a sequence of SSE
events:

1. Parse the name and optional `work`, `institute`, and `image` inputs.
2. Run up to four query variants through Google CSE when configured, otherwise
   DuckDuckGo HTML search.
3. Probe public social and reference sources.
4. Derive probable usernames and probe account templates concurrently.
5. Search research and academic sources.
6. Search public comments, posts, and discussions.
7. Generate reverse-image-search links when an image URL was supplied.
8. Harvest public image results.
9. Deduplicate and categorize results, generate a TF-IDF-lite tag cloud, and
   identify possible homonym groups.
10. Compute PeopleRank and stream summary statistics.

The frontend consumes `start`, `progress`, `results`, `social`, `accounts`,
`research`, `comments`, `visual`, `images`, `tags`, `rank`, `stats`, `done`,
and `error` events.

### 4.3 Email-intelligence pipeline

`GET /api/email-lookup?email=...` validates the address and streams a separate
investigation. The stages include local-part/name parsing, domain and MX
analysis, Gravatar, reputation, breach checks, GitHub association, social
correlation, web dorking, Reddit, domain WHOIS, profile photos, generated
usernames, and a final score summary.

The email endpoint treats external-service failures as per-stage failures and
continues the investigation, while fatal generator errors are emitted as an
SSE `error` event.

### 4.4 ZLens architecture

ZLens has two related operating modes:

- **Local index mode:** images are validated, normalized, indexed in SQLite,
  and searched using exact SHA-256 equality plus pHash/dHash Hamming-distance
  thresholds.
- **Live candidate mode:** Bing image result pages provide candidate URLs;
  candidate images are downloaded, independently preprocessed, and accepted
  only when their measured hash or tensor similarity meets the configured
  thresholds.

The preprocessor rejects unsupported or malformed content by checking magic
bytes and Pillow decoding, enforces a 15 MB default file limit, enforces a
25-megapixel default limit and 32-pixel minimum dimension, normalizes EXIF
orientation and color mode, strips EXIF metadata, and creates:

- SHA-256 over sanitized JPEG bytes.
- 64-bit dHash.
- 64-bit aHash.
- 64-bit pHash based on a 2D DCT.
- A normalized `(3, 224, 224)` float32 tensor representation.

The persistent schema contains `assets` and `asset_sources`. SQLite is
configured for foreign keys and WAL mode. Asset provenance is retained without
returning raw image bytes or absolute host filesystem paths.

## 5. HTTP API inventory

### General and people search

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/` | Serves the frontend SPA. |
| `GET` | `/api/search` | Streams the name/keyword OSINT investigation over SSE. |
| `GET` | `/api/suggest` | Returns parsed query variants for short autocomplete input. |
| `GET` | `/api/email-lookup` | Streams email intelligence over SSE. |
| `GET` | `/api/health` | Returns backend health and feature/configuration status. |

### ZLens

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/zlens/health` | Reports image validation and ZLens health information. |
| `GET` | `/api/zlens/status` | Reports local collection status. |
| `POST` | `/api/zlens/upload` | Validates and ingests a query image into a temporary session. |
| `GET` | `/api/zlens/session/<id>/preview` | Previews an uploaded session image. |
| `GET` | `/api/zlens/stream` | Streams ZLens candidate-search progress. |
| `DELETE` | `/api/zlens/search/<id>` | Deletes an in-memory ZLens query session. |
| `POST` | `/api/zlens/search` | Searches indexed/local and live image candidates. |
| `GET` | `/api/zlens/index/stats` | Returns indexed asset and source counts. |
| `POST` | `/api/zlens/index/import` | Imports a permitted dataset subdirectory. |
| `GET` | `/api/zlens/index/assets` | Returns paginated indexed asset metadata. |
| `POST` | `/api/zlens/index` | Indexes the built-in collection. |
| `GET` | `/api/zlens/assets/<id>/preview` | Safely previews an indexed asset. |

Compatibility aliases also exist at `/api/status`, `/api/index`,
`/api/search` for `POST` requests, and `/asset/<id>`.

## 6. Core algorithms and data processing

### 6.1 Query parsing and search

`QueryParser` creates normalized name components and query variants. The
search engine caps each multi-search at four variants and deduplicates results
by URL. Requests use bounded timeouts, rotating user agents, and small delays
between searches to reduce unnecessary request pressure.

### 6.2 Entity resolution

`EntityResolver` maps domains to categories such as professional, social,
academic, reference, blog, and news. It deduplicates URLs, groups results,
creates a weighted tag cloud from titles and descriptions using a TF-IDF-like
calculation, and flags possible homonyms by grouping recurring contextual
keywords. The homonym logic is heuristic and is not an identity assertion.

### 6.3 PeopleRank

`PeopleRanker` assigns a score from 0 to 100 across six dimensions:

| Dimension | Maximum |
|---|---:|
| Result volume | 20 |
| Domain diversity | 15 |
| Social presence | 25 |
| Authority sources | 15 |
| Image presence | 10 |
| Keyword relevance | 15 |

Scores are descriptive visibility indicators, not measures of identity,
credibility, intent, or truthfulness. The result is mapped to grades `S`, `A`,
`B`, `C`, `D`, or `F`.

### 6.4 Local visual retrieval

Local ZLens search first performs exact SHA-256 lookup, then scans indexed
perceptual hashes. Strong near-duplicates require pHash distance at most 6 and
dHash distance at most 4. Weak perceptual variants require both distances at
most 8. Exact matches rank ahead of strong near-duplicates, which rank ahead
of weak variants. Results include provenance and explicit verification labels.

## 7. Frontend

The frontend is implemented with HTML, CSS, and modern browser JavaScript.
`app.js` manages the people-search state, SSE lifecycle, result rendering,
filters, tag cloud, PeopleRank display, comments, image strip, JSON export, and
print reporting. `lookmeup.js` handles the email-intelligence view.
`zlens.js` manages drag-and-drop image ingestion, validation telemetry,
index-stat refresh, platform filters, live search progress, and match display.

The interface exposes four product areas:

- OSINT Search
- LookMeUp
- Recruiter
- ZLens

The frontend does not require a separate compile step. Static assets are served
directly by Flask.

## 8. Dependencies and configuration

The runtime dependencies are Flask, Flask-CORS, Requests, BeautifulSoup4,
lxml, python-dotenv, urllib3, Pillow, and NumPy. Python 3.10+ is documented,
with the application branding indicating Python 3.11+.

Supported environment variables include:

| Variable | Effect |
|---|---|
| `FLASK_PORT` | Flask listening port; defaults to `5000`. |
| `FLASK_ENV` | Enables development debug mode when set to `development`. |
| `REQUEST_TIMEOUT` | Default outbound request timeout for several modules. |
| `MAX_RESULTS_PER_SOURCE` | Default search result cap. |
| `GOOGLE_API_KEY` | Enables Google Custom Search. |
| `GOOGLE_CSE_ID` | Selects the Google Custom Search engine. |
| `LENSO_API_KEY` | Optional Lenso.ai integration credential. |
| `LENSO_API_URL` | Optional Lenso.ai endpoint override. |
| `ZLENS_DB_PATH` | SQLite database path override. |
| `ZLENS_PERMITTED_DATASET_DIR` | Permitted local image dataset directory. |

`run.ps1` creates `backend/.venv`, installs `requirements.txt`, copies
`.env.example` to `.env` when available, and launches `backend/app.py`.

## 9. Testing and verification

The repository includes focused tests for:

- Flask ZLens API behavior.
- Image validation, magic-byte checks, limits, and preprocessing.
- SQLite indexing, duplicate handling, provenance, and path security.
- Exact and perceptual retrieval behavior.
- Web dorking and optional Lenso client behavior.
- Milestone verification and starter retrieval benchmarks.

The test files are under `TruSINT/backend/tests/`. Most tests use synthetic
images and temporary databases, which keeps deterministic local retrieval tests
independent from the production collection.

External-provider behavior remains environment- and network-dependent. Live
search providers may rate-limit, change HTML structures, return incomplete
results, or be unavailable during tests.

## 10. Security, privacy, and operational considerations

Positive controls present in the implementation include:

- Input validation for email addresses and image payloads.
- Magic-byte validation rather than trusting file extensions or MIME types.
- Image size, pixel-count, and minimum-dimension limits.
- EXIF stripping before normalized image hashing.
- Temporary upload cleanup in request finalizers.
- Permitted-directory checks for local dataset indexing and preview.
- Parameterized SQLite queries and foreign-key enforcement.
- No exposure of absolute database paths through asset metadata.
- Explicit refusal to fabricate visual matches when candidate images cannot be
  downloaded or validated.
- CORS restricted to API paths, although those paths currently allow all
  origins.

Operational risks and limitations include:

- Several endpoints perform unauthenticated external lookups and can consume
  outbound network resources.
- The application has no authentication or authorization layer in the current
  codebase.
- CORS for `/api/*` is configured with `origins: "*"`, which should be
  restricted before deployment beyond a trusted local environment.
- In-memory ZLens sessions do not survive process restarts and are not shared
  across multiple workers.
- Many source integrations rely on public APIs or HTML scraping and can break
  when provider policies or page structures change.
- Name matching, username derivation, homonym grouping, and score calculation
  can produce false positives and must not be treated as identity proof.
- The current local perceptual retrieval scan is a full table scan; a large
  collection will require an ANN/vector index or other search optimization.
- Secrets should be supplied through deployment configuration and must not be
  committed to `.env` or source control.

## 11. Recommended next steps

1. Move the detailed project overview into the root `README.md` or link it to
   this report so the repository landing page is self-documenting.
2. Add production configuration for authentication, rate limiting, structured
   audit logging, restrictive CORS, and a non-debug WSGI server.
3. Add provider adapters with contract tests and clearer attribution/rate-limit
   handling for external sources.
4. Expand API tests for SSE event ordering, malformed parameters, timeout
   behavior, and error responses.
5. Replace the ZLens full-table perceptual scan with an indexed similarity
   structure when the permitted dataset grows materially.
6. Add explicit data-retention controls and deployment documentation for
   uploads, SQLite files, logs, and exported reports.

## 12. Conclusion

TruSINT is a feature-rich prototype-to-application OSINT platform with a
well-defined streaming search experience and a comparatively disciplined local
image-ingestion pipeline. Its strongest engineering features are the
modular source adapters, incremental SSE UX, transparent scoring, SQLite
provenance model, strict image validation, and non-fabricating visual matching
rules. The largest production gaps are access control, rate limiting,
provider resilience, test isolation from live services, and scalability of
perceptual search.
