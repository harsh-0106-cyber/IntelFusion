# IntelFusion — OSINT People Search Engine

<div align="center">

```
  ████████████████████████████████████████
  █  IntelFusion  OSINT  Search  Engine  █
  ████████████████████████████████████████
```

**A professional WebMii-style OSINT aggregator** that dynamically searches publicly
available information across 10+ platforms and surfaces a comprehensive intelligence
profile — including a PeopleRank™ visibility score — in real-time.

[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square&logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-green?style=flat-square&logo=flask)](https://flask.palletsprojects.com)
[![License](https://img.shields.io/badge/License-MIT-violet?style=flat-square)](LICENSE)

</div>

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔍 **Multi-Source Search** | DuckDuckGo search mashup — no API key required |
| 📡 **Social Probing** | GitHub, Reddit, Wikipedia (public APIs) + LinkedIn, Twitter, Instagram, Facebook, YouTube, Medium, Quora (site-targeted) |
| 🖼️ **Image Harvesting** | Public image search for profile photos |
| 🏷️ **TF-IDF Tag Cloud** | Auto-generated topic keywords from aggregated text |
| 📊 **PeopleRank™** | 0–100 online visibility score with grade (S/A/B/C/D/F) |
| 🔁 **Entity Resolution** | Deduplication, category grouping, homonym detection |
| ⚡ **SSE Streaming** | Results stream into the UI live as each stage completes |
| 📄 **Export** | JSON download + browser print report |
| 🌑 **Premium Dark UI** | Glassmorphism, animated radar loader, neon accents |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Windows / macOS / Linux

### One-Click Launch (Windows PowerShell)
```powershell
cd "e:\Intelfusion(OSINT Project)\IntelFusion"
.\run.ps1
```
Then open **http://localhost:5000** in your browser.

### Manual Start
```bash
cd backend
pip install -r requirements.txt
python app.py
```

---

## 🏗️ Architecture

```
IntelFusion/
├── backend/
│   ├── app.py                    ← Flask API + SSE streaming
│   ├── requirements.txt
│   ├── .env.example              ← Optional API keys config
│   └── osint/
│       ├── query_parser.py       ← Parses name + keywords
│       ├── search_engine.py      ← DuckDuckGo + Google CSE
│       ├── social_prober.py      ← 10 platform probes
│       ├── image_harvester.py    ← DDG image search
│       ├── entity_resolver.py    ← Dedup + tag cloud + homonyms
│       └── people_rank.py        ← PeopleRank™ score (0-100)
├── frontend/
│   ├── index.html                ← Single-page application
│   ├── css/style.css             ← Premium dark design system
│   └── js/app.js                 ← SSE handler + UI rendering
└── run.ps1                       ← One-click launcher
```

### Five-Stage OSINT Pipeline

```
User Input → QueryParser → SearchEngine (DDG/Google) → SocialProber (10 platforms)
  → ImageHarvester → EntityResolver (dedup + tags + homonyms) → PeopleRanker → SSE Stream → UI
```

---

## 🔑 Optional API Keys

IntelFusion works **without any API keys** using DuckDuckGo's public HTML endpoint.
For better results you can optionally add:

| Service | How to Get | Benefit |
|---|---|---|
| Google Custom Search | [console.developers.google.com](https://console.developers.google.com) | More accurate results |
| SerpAPI | [serpapi.com](https://serpapi.com) | Anti-bot bypass |

Add keys to `backend/.env`:
```env
GOOGLE_API_KEY=your_key
GOOGLE_CSE_ID=your_cse_id
```

---

## 📊 PeopleRank™ Score

| Grade | Range | Meaning |
|---|---|---|
| **S** | 85–100 | Highly Prominent — authority-level online presence |
| **A** | 70–84  | Well Established — strong cross-platform coverage |
| **B** | 55–69  | Moderately Visible — present across several platforms |
| **C** | 35–54  | Limited Visibility — sparse online presence |
| **D** | 15–34  | Sparse Presence — very few public records |
| **F** | 0–14   | Virtually Unknown — minimal online footprint |

Score dimensions: Result Volume (20) · Domain Diversity (15) · Social Presence (25) · Authority Sources (15) · Image Presence (10) · Keyword Relevance (15)

---

## ⚖️ Legal & Ethical Notice

> **IntelFusion searches only publicly available information.**
> This tool is intended for educational, journalistic, and legitimate investigative use.
> - It does **not** bypass login walls, access private data, or store any results.
> - All queries respect the spirit of `robots.txt` where feasible.
> - Do **not** use this tool to harass, stalk, or harm individuals.
> - Respect all applicable privacy laws (GDPR, CCPA, etc.).

---

## 🛠️ Tech Stack

- **Backend**: Python 3.11, Flask 3, BeautifulSoup4, Requests
- **Frontend**: Vanilla HTML5, CSS3, JavaScript (ES2022+) — zero frameworks
- **Fonts**: Space Grotesk, Inter, JetBrains Mono (Google Fonts)
- **Streaming**: Server-Sent Events (SSE)

---

*Built with ❤️ for cybersecurity education and research.*
