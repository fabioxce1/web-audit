# WebAudit — Comprehensive Website Auditing Tool

**WebAudit** is a desktop application for full-site auditing. It maps every URL on a domain and analyzes them for cybersecurity, SEO, performance, active pentesting, and generates professional PDF reports.

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-blue" alt="Python">
  <img src="https://img.shields.io/badge/fastapi-0.110+-green" alt="FastAPI">
  <img src="https://img.shields.io/badge/react-18-blue" alt="React">
  <img src="https://img.shields.io/badge/electron-30+-9cf" alt="Electron">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="License">
</p>

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [System Modules](#system-modules)
- [Installation](#installation)
- [Usage](#usage)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [API Endpoints](#api-endpoints)
- [Configuration](#configuration)
- [Legal Disclaimer](#legal-disclaimer)
- [Roadmap](#roadmap)
- [License](#license)

---

## Features

### 🕷️ Crawler + URL Mapping
- Concurrent BFS discovery of all internal domain URLs
- Link extraction from `<a>`, `<iframe>`, `<form>`, `<area>` tags
- `sitemap.xml` and `robots.txt` parsing
- JavaScript rendering with Playwright for SPAs
- Smart deduplication (URL normalization, tracking params, SHA256 content hashing)
- Pattern-based exclusion (tags, categories, feeds, date archives)
- Hierarchical URL tree with parent-child relationships
- Real-time progress via WebSocket
- Directory enumeration (admin paths, .env, backups, etc.)

### 🔒 Cybersecurity
- **HTTP Headers**: CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
- **SSL/TLS**: Certificate validity, expiration date, TLS version, issuer
- **Cookies**: Secure, HttpOnly, SameSite flags
- **CORS**: Wildcard `*` detection, arbitrary origin with credentials
- **WAF Detection**: Cloudflare, Sucuri, ModSecurity, AWS WAF, Imperva, Akamai, F5, Barracuda
- **Open Ports**: TCP scan of 20 common ports (FTP, SSH, MySQL, Redis, etc.)
- **Email Security**: SPF and DMARC via DNS queries
- **HTTPS Enforcement**: HTTP→HTTPS redirect verification
- **Info Disclosure**: Emails, API keys, passwords, JWTs, AWS keys in HTML
- **Tech Detection**: CMS, frameworks, servers (WordPress, PHP, Vue, React, etc.)
- **Access Control**: Public admin panels, rate limiting visibility
- **0-100 Scoring** with per-domain deduplication

### ⚔️ Active Pentesting
- **Injections**: SQL, NoSQL, Command Injection, and LDAP in forms and URL parameters
- **Reflected XSS**: Payload testing in forms and query params
- **SSRF**: Detection of parameters accepting external URLs
- **BOLA/IDOR**: Numeric ID iteration in URLs to detect unauthorized access
- **Mass Assignment**: Sends extra fields (role, is_admin) to sensitive forms
- **Data Exposure**: Analyzes REST/GraphQL APIs for exposed sensitive fields

### 📈 SEO Analyzer
- **Meta Tags**: Title, Description, Viewport, Robots (noindex/nofollow)
- **Open Graph**: og:title, og:description, og:image, og:url, og:type
- **Twitter Cards**: twitter:card, title, description, image
- **Technical SEO**: Canonical URL, external links without nofollow
- **Headings**: H1-H4 structure, uniqueness, hierarchy
- **Images**: Alt text, lazy loading
- **Content**: Word count, thin content detection
- **Structured Data**: JSON-LD, Microdata, Schema.org types
- **Performance**: Response time, page size
- **0-100 Scoring** per page with detailed analysis

### 📊 Reporting & Export
- **Dashboard**: Consolidated Security + SEO scores with severity breakdowns
- **PDF Export**: Professional audit report with cover page, score summary, findings by severity, actionable recommendations, and methodology section
- **JSON Export**: Full structured data export with all scan checks for integration with other tools
- **Project Summary**: URLs mapped, crawled, check counts, scan status

---

## Architecture

```
┌──────────────────────────────────────────────┐
│  Electron Desktop App (Frontend)             │
│  - React 18 + Tailwind CSS UI                │
│  - Dashboard, tabs, charts                   │
│  - Real-time progress via WebSocket          │
└──────────────────┬───────────────────────────┘
                   │ HTTP + WS (localhost:8000)
┌──────────────────▼───────────────────────────┐
│  Python FastAPI (Backend Engine)             │
│  ┌─────────────────────────────────────────┐ │
│  │ Module 1: Crawler + URL Mapping         │ │
│  │ Module 2: Security Scanner              │ │
│  │ Module 3: SEO Analyzer                  │ │
│  │ Module 4: Active Pentesting             │ │
│  │ Module 5: Reporting & Export            │ │
│  └─────────────────────────────────────────┘ │
│  - SQLAlchemy + aiosqlite (SQLite)           │
│  - Async crawling with httpx                 │
│  - Playwright (headless browser JS)          │
└──────────────────────────────────────────────┘
```

---

## Installation

### Prerequisites

- **Python 3.12+**
- **Node.js 18+**
- **npm**
- **Playwright** (optional, for JS rendering)

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/webaudit.git
cd web-audit
```

### 2. Backend (Python)

```bash
cd backend

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate   # macOS / Linux
# venv\Scripts\activate    # Windows

pip install -r requirements.txt
pip install 'uvicorn[standard]'

# Optional: Playwright for JS rendering
pip install playwright
playwright install chromium
```

> **Windows users:** use `python` instead of `python3`, and `venv\Scripts\activate` instead of `source venv/bin/activate`.

### 3. Frontend (Electron + React)

```bash
cd desktop
npm install
```

### 4. Run

**Backend** (in one terminal):
```bash
cd backend
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend** (in another terminal):
```bash
cd desktop
npm run dev
```

The app will be available at `http://localhost:5173` (Vite dev server).

For production builds:
```bash
cd desktop
npm run build
```

---

## Usage

### 1. Create a Project
Click "New Project", enter a name and the seed URL of the site to audit.

### 2. Start Crawling
In the project detail view, click "Start Crawling". The BFS engine will traverse the site discovering all internal URLs.

### 3. Analyze Results
Once crawling is complete:

| Tab | What it does |
|---|---|
| **URLs** | Table with all URLs, status filters, broken/OK toggles, external links |
| **Security** | Click "Start Security Scan" — analyzes headers, SSL, cookies, WAF, CORS, ports, pentesting |
| **SEO** | Click "Start SEO Analysis" — audits meta tags, headings, images, content, performance |
| **Dashboard** | Combined Security + SEO scores, project summary, PDF/JSON export |

### 4. View URL Tree
Click "View Tree" to visualize the site's hierarchical structure with status indicators.

### Troubleshooting

| Issue | macOS / Linux | Windows |
|---|---|---|
| Port 8000 already in use | `lsof -ti :8000 \| xargs kill -9` | `netstat -ano \| findstr :8000` then `taskkill /PID <PID> /F` |
| Python not found | Use `python3` or `python3.12` | Use `python` or `py -3` |
| Playwright not found | `pip install playwright && playwright install chromium` | Same (use `pip` or `pip3`) |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 + FastAPI |
| Async Runtime | asyncio + httpx |
| Database | SQLite via SQLAlchemy + aiosqlite |
| Headless Browser | Playwright for Python |
| Desktop Shell | Electron 30+ |
| UI Framework | React 18 + Tailwind CSS |
| Communication | REST API + WebSocket |
| DNS Queries | dnspython |
| HTML Parsing | BeautifulSoup4 + lxml |

---

## Project Structure

```
web-audit/
├── README.md
├── REQUIREMENTS.md
├── backend/
│   ├── requirements.txt
│   ├── pyproject.toml
│   ├── data/                    # SQLite DB + snapshots
│   └── app/
│       ├── main.py              # FastAPI entrypoint
│       ├── config.py            # Settings (env vars)
│       ├── db.py                # SQLAlchemy async engine
│       ├── models/
│       │   ├── project.py       # Project, CrawlSession
│       │   ├── url.py           # DiscoveredURL
│       │   ├── security.py      # SecurityScan, SecurityCheck
│       │   └── seo.py           # SeoScan, SeoCheck
│       ├── crawler/
│       │   ├── engine.py        # BFS crawler orchestrator
│       │   ├── fetcher.py       # HTTP + Playwright fetchers
│       │   ├── parser.py        # HTML link extraction
│       │   ├── normalizer.py    # URL normalization + dedup
│       │   ├── sitemap.py       # Sitemap.xml parser
│       │   ├── robots.py        # robots.txt + politeness
│       │   ├── dirlist.py       # Directory enumeration wordlist
│       │   └── enumerator.py    # Dir enumeration scanner
│       ├── security/
│       │   └── scanner.py       # Security scanner (headers, SSL, WAF, etc.)
│       ├── pentest/
│       │   ├── payloads.py      # SQL, XSS, SSRF, NoSQL, CMD payloads
│       │   └── scanner.py       # Active pentest scanner
│       ├── seo/
│       │   └── scanner.py       # SEO analyzer
│       ├── reports/
│       │   └── generator.py     # PDF & JSON report generator
│       └── api/
│           ├── projects.py      # Project CRUD
│           ├── crawl.py         # Crawl control + WebSocket
│           ├── security.py      # Security scan endpoints
│           ├── seo.py           # SEO scan endpoints
│           └── reports.py       # Dashboard & export endpoints
└── desktop/
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    └── src/
        ├── main/                # Electron main process
        │   ├── index.ts         # Window creation
        │   ├── python.ts        # Python process manager
        │   └── preload.ts       # Context bridge
        └── renderer/
            ├── App.tsx
            ├── pages/
            │   ├── Home.tsx           # Project list
            │   ├── ProjectDetail.tsx   # Dashboard (URLs, Security, SEO)
            │   └── UrlTree.tsx        # Hierarchical tree
            ├── components/
            │   ├── UrlTable.tsx       # URL table with filters
            │   ├── CrawlProgress.tsx  # Live progress bar
            │   ├── SecurityPanel.tsx  # Security findings
            │   ├── SeoPanel.tsx       # SEO findings
            │   └── DashboardPanel.tsx # Dashboard + export
            └── lib/
                └── api.ts             # API client + types
```

---

## API Endpoints

### Projects
| Method | Route | Description |
|---|---|---|
| POST | `/api/projects` | Create project |
| GET | `/api/projects` | List all projects |
| GET | `/api/projects/:id` | Get project details |
| DELETE | `/api/projects/:id` | Delete project |

### Crawling
| Method | Route | Description |
|---|---|---|
| POST | `/api/projects/:id/crawl` | Start crawling |
| POST | `/api/projects/:id/crawl/stop` | Stop crawling |
| GET | `/api/projects/:id/urls` | List URLs (paginated, filterable) |
| GET | `/api/projects/:id/tree` | Hierarchical URL tree |
| GET | `/api/projects/:id/stats` | Session statistics |
| WS | `/api/projects/ws/:id/crawl` | Real-time crawl progress |

### Security
| Method | Route | Description |
|---|---|---|
| POST | `/api/projects/:id/security/scan` | Start security scan |
| GET | `/api/projects/:id/security/scan` | Latest scan |
| GET | `/api/projects/:id/security/checks` | Findings (filterable, paginated) |
| GET | `/api/projects/:id/security/summary` | Summary + scoring |

### SEO
| Method | Route | Description |
|---|---|---|
| POST | `/api/projects/:id/seo/scan` | Start SEO analysis |
| GET | `/api/projects/:id/seo/scan` | Latest analysis |
| GET | `/api/projects/:id/seo/checks` | Findings (filterable, paginated) |
| GET | `/api/projects/:id/seo/summary` | Summary + scoring |

### Reports & Export
| Method | Route | Description |
|---|---|---|
| GET | `/api/projects/:id/dashboard` | Consolidated dashboard (security + SEO scores) |
| GET | `/api/projects/:id/export/json` | Full structured JSON export (all checks) |
| GET | `/api/projects/:id/export/pdf` | Professional PDF audit report |

---

## Configuration

Each project accepts custom configuration via JSON:

```json
{
  "user_agent": "WebAudit/1.0",
  "max_workers": 5,
  "crawl_delay": 1.0,
  "respect_robots_txt": true,
  "use_playwright": true,
  "timeout": 15,
  "max_urls": 500,
  "max_depth": 0,
  "enumerate_dirs": true,
  "exclude_patterns": [
    "/tag/", "/category/", "/feed/", "/wp-content/",
    "/page/", "/?s=", "/comments/"
  ],
  "save_html_snapshots": true
}
```

Environment variables (`WEB_AUDIT_` prefix):
```bash
WEB_AUDIT_DB_PATH=./data/web_audit.db
WEB_AUDIT_MAX_WORKERS=5
WEB_AUDIT_TIMEOUT=15
WEB_AUDIT_MAX_URLS=500
```

---

## Legal Disclaimer

WebAudit is designed **exclusively for auditing websites over which the user has explicit authorization** (owned sites or client sites with consent).

Unauthorized use of this tool against third-party sites may violate local and international laws. The developer is not responsible for misuse of the application.

---

## Roadmap

- [x] Module 1: Crawler + URL Mapping
- [x] Module 2: Security Scanner
- [x] Module 3: SEO Analyzer
- [x] Module 4: Active Pentesting
- [x] Module 5: Reporting & Export (PDF, JSON, Dashboard)
- [ ] Installable packaging (Windows, macOS, Linux)
- [ ] Audit history and comparisons
- [ ] Known CVE detection


---

## License

MIT License.
