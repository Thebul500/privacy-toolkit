# Privacy Toolkit

[![CI](https://github.com/Thebul500/privacy-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/Thebul500/privacy-toolkit/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-256%20passing-brightgreen.svg)](#testing)

**Open-source personal data removal platform.** Discover your digital footprint across 78 data brokers and people-search sites, send legally-compliant CCPA/GDPR deletion requests, and track removal progress with automated verification and re-listing detection.

Privacy Toolkit gives you the same capabilities as paid services like DeleteMe ($129/yr), Incogni ($78/yr), and Optery ($249/yr) — without the subscription.

---

## Table of Contents

- [Key Features](#key-features)
- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [Scanners](#scanners)
- [Usage](#usage)
- [Web Dashboard](#web-dashboard)
- [Configuration](#configuration)
- [Broker Database](#broker-database)
- [Security](#security)
- [Architecture](#architecture)
- [CI/CD Pipeline](#cicd-pipeline)
- [Testing](#testing)
- [Roadmap](#roadmap)
- [License](#license)

---

## Key Features

### Discovery & Scanning
- **Multi-vector scanning** — emails, usernames, phone numbers, and addresses across data brokers, breach databases, and social platforms
- **7 integrated scanners** — HIBP, Holehe, Sherlock, Maigret, PhoneInfoga, PeopleSearch (Playwright), SpiderFoot
- **Account discovery** — find accounts linked to your identity with interactive removal guidance
- **Breach exposure reports** — aggregate breach data with risk assessment (HIGH/MEDIUM/LOW)
- **Result deduplication** — unique index prevents duplicate findings across repeated scans

### Automated Removal
- **78 pre-configured data brokers** — Whitepages, Spokeo, BeenVerified, Intelius, and 74 more
- **Email removal requests** — SMTP with legal templates citing CCPA, GDPR, CPRA, VCDPA, CPA, CTDPA, TDPSA
- **Form-based opt-outs** — headless Chromium automation via Playwright with screenshot proof
- **CAPTCHA solving** — integrated 2captcha and capsolver support for automated form submissions
- **40 service deletion guides** — step-by-step instructions for Facebook, Google, LinkedIn, Steam, and more

### Anti-Detection
- **Stealth browser** — playwright-stealth patches with `--disable-blink-features=AutomationControlled` to bypass headless detection
- **User-Agent rotation** — 10 realistic browser fingerprints rotated per request
- **Fingerprint randomization** — randomized viewport, locale, and timezone per session
- **Consent wall dismissal** — auto-clicks cookie banners and "Continue to Results" gates
- **Request jitter** — randomized delays to avoid rate-limiting and fingerprinting
- **Proxy support** — HTTP and SOCKS5 proxy passthrough for all Playwright operations
- **Fallback CSS selectors** — secondary selectors on key broker sites when primary selectors break
- **Universal name matching** — content-based fallback detects listings even when CSS selectors are stale

### Monitoring & Verification
- **Post-removal verification** — automated re-scanning of brokers to confirm deletion
- **Re-listing detection** — scheduled rescans catch brokers that re-add your data
- **Privacy score** — 0-100 score with letter grade (A-F) based on exposure metrics
- **Score trending** — 7-day and 30-day trend tracking with dashboard indicators
- **Selector health check** — validate that broker site CSS selectors still work

### Reporting & Notifications
- **PDF, CSV, JSON, HTML export** — generate compliance-ready reports
- **Signal notifications** — scan completion and removal alerts via Signal REST API
- **Webhook notifications** — POST JSON payloads to any endpoint (Slack, Discord, n8n, etc.)
- **Web dashboard** — FastAPI + HTMX interface with real-time scan status
- **CLI with progress bars** — full-featured Click CLI with Rich output

### Security
- **bcrypt authentication** — password hashing with session management and 24h expiry
- **CSRF protection** — double-submit cookie pattern (OWASP)
- **Security headers** — HSTS, X-Frame-Options, CSP, Referrer-Policy
- **Path traversal prevention** — input validation on all file operations
- **Sandboxed templates** — Jinja2 auto-escaping with SRI-pinned CDN scripts

---

## How It Works

```
                                    Privacy Toolkit

    1. DISCOVER                    2. REMOVE                     3. VERIFY

    Scan your identity          Send deletion requests        Confirm removal
    across 78 brokers           via email and web forms       with automated rescans

    ┌──────────────┐           ┌──────────────────┐          ┌──────────────┐
    │  HIBP        │           │  CCPA/GDPR Email │          │  Re-scan     │
    │  Holehe      │     →     │  Playwright Form │    →     │  Verify      │
    │  Sherlock    │           │  CAPTCHA Solve   │          │  Score       │
    │  Maigret     │           │  Follow-up       │          │  Alert       │
    │  PhoneInfoga │           └──────────────────┘          └──────────────┘
    │  PeopleSearch│
    └──────────────┘
```

1. **Create a profile** with your personal identifiers (name, emails, phones, usernames, addresses)
2. **Run a full scan** — Privacy Toolkit queries all integrated scanners and records findings
3. **Review findings** — see which brokers have your data, with confidence levels and source details
4. **Send removal requests** — automated CCPA/GDPR emails and form submissions with legal citations
5. **Track progress** — monitor removal status (pending → submitted → confirmed)
6. **Verify removals** — automated re-scanning confirms brokers actually deleted your data
7. **Get alerts** — notifications when removals are confirmed or when data reappears

---

## Quick Start

### Prerequisites

- Python 3.12+
- Chromium (installed automatically by Playwright)
- SMTP credentials for sending deletion emails (Gmail App Password recommended)

### Install

```bash
git clone https://github.com/Thebul500/privacy-toolkit.git
cd privacy-toolkit
bash install.sh
```

The installer creates a virtual environment, installs all dependencies (including bcrypt and xhtml2pdf), downloads PhoneInfoga, installs Playwright Chromium, and creates the `privacy-toolkit` CLI entry point.

### Docker

```bash
cp .env.example .env
# Edit .env with your credentials

docker-compose up -d
# Web UI at http://localhost:8384
```

### First Run

```bash
# Check all dependencies
privacy-toolkit doctor deps

# Interactive setup wizard (also available at /setup in the web UI)
privacy-toolkit profile create myname

# Run your first scan
privacy-toolkit scan full -p myname

# See what was found
privacy-toolkit report -p myname
```

---

## Scanners

| Scanner | What It Finds | Input | Source |
|---------|---------------|-------|--------|
| **HaveIBeenPwned** | Data breaches and paste exposures | Email | HIBP API |
| **Holehe** | Email registrations across 120+ services | Email | holehe |
| **Sherlock** | Username presence on 300+ sites | Username | sherlock-project |
| **Maigret** | Advanced username OSINT on 2500+ sites | Username | maigret |
| **PhoneInfoga** | Phone number carrier and location intel | Phone | phoneinfoga |
| **PeopleSearch** | Data broker profile listings | Name, phone, email, address | Playwright + Chromium |
| **SpiderFoot** | Full OSINT framework (optional) | Any | Docker container |

---

## Usage

### Scanning

```bash
# Full scan across all scanners
privacy-toolkit scan full -p myname

# Individual scan types
privacy-toolkit scan email user@example.com
privacy-toolkit scan username johndoe
privacy-toolkit scan phone +15551234567
privacy-toolkit scan people "John Doe" --type name
```

### Account Discovery

```bash
# Find accounts linked to an email
privacy-toolkit accounts find-by-email user@example.com

# Breach exposure report for all profile emails
privacy-toolkit accounts exposure-report -p myname
```

### Removal Requests

```bash
# Preview (dry run)
privacy-toolkit remove email-request -p myname --dry-run

# Send CCPA/GDPR deletion emails
privacy-toolkit remove email-request -p myname

# Automated form submission via Playwright
privacy-toolkit remove form-request -p myname -b spokeo

# Manual removal instructions
privacy-toolkit remove manual -p myname
```

### Tracking & Verification

```bash
# View all removal requests
privacy-toolkit track status -p myname

# Run post-removal verification scans
privacy-toolkit track verify -p myname

# Check for overdue responses
privacy-toolkit track pending -p myname

# Mark a removal as confirmed
privacy-toolkit track confirm 42
```

### Reports

```bash
# Terminal table
privacy-toolkit report -p myname

# Export formats
privacy-toolkit report -p myname -f pdf -o report.pdf
privacy-toolkit report -p myname -f json -o report.json
privacy-toolkit report -p myname -f csv -o report.csv
privacy-toolkit report -p myname -f html -o report.html
```

### Scheduling

```bash
# Enable automated re-scanning (cron)
privacy-toolkit schedule enable -p myname

# View schedule
privacy-toolkit schedule status
```

Default: full re-scan weekly (Sunday 3 AM), pending recheck daily (9 AM), verification daily (11 AM), follow-ups after 45 days.

### Diagnostics

```bash
# Check all dependencies
privacy-toolkit doctor deps

# Test broker CSS selectors
privacy-toolkit doctor check-selectors
```

---

## Web Dashboard

Start the web server:

```bash
privacy-toolkit web
# → http://localhost:8080
```

The dashboard provides:

| Page | Description |
|------|-------------|
| **Dashboard** | Privacy score with trend arrows, stats overview, active tasks, PDF downloads |
| **Profiles** | Create and manage identity profiles |
| **Scans** | Trigger scans with live HTMX status updates |
| **Accounts** | Discover linked accounts by email/phone/username |
| **Removals** | Track all requests, submit new batches, confirm/reappear |
| **Brokers** | Browse 78 brokers, check listing status, verify selectors |
| **Activity** | Audit log of all actions |

First-time users are guided through a **setup wizard** to configure SMTP, create a profile, and run an initial scan.

---

## Configuration

```bash
cp config/config.yaml.example config/config.yaml
```

```yaml
# SMTP for sending deletion emails
smtp:
  host: smtp.gmail.com
  port: 587
  username: you@gmail.com
  password: "${SMTP_PASSWORD}"    # Env var resolution

# Optional: HIBP API key for breach detection
hibp_api_key: "${HIBP_API_KEY}"

# Optional: Signal notifications
signal:
  enabled: true
  api_url: "http://127.0.0.1:8082"
  sender: "${SIGNAL_SENDER}"
  recipients: ["+1234567890"]

# Optional: Webhook notifications (Slack, Discord, n8n, etc.)
webhook:
  enabled: true
  url: "https://hooks.slack.com/services/..."
  headers:
    Authorization: "Bearer ${WEBHOOK_TOKEN}"

# Optional: CAPTCHA solving
captcha:
  provider: "2captcha"           # "2captcha", "capsolver", or "none"
  api_key: "${CAPTCHA_API_KEY}"

# Browser automation settings
browser:
  headless: true
  timeout: 30000
  rate_limit_delay: 2.0
  proxy:
    server: "${PROXY_URL}"       # HTTP or SOCKS5
    username: "${PROXY_USER}"
    password: "${PROXY_PASS}"
```

Secrets support three formats:
```yaml
password: "literal-value"         # Used as-is
password: "${SMTP_PASSWORD}"      # Resolved from environment variable
password: ""                      # Auto-fallback to env var by convention
```

---

## Optional APIs

Privacy Toolkit works fully out of the box with no paid services. The core scanning, stealth browser, consent wall dismissal, name-match detection, and CCPA/GDPR email removal all work for free. Optional paid APIs extend coverage:

| API | What It Does | Cost | Required? |
|-----|-------------|------|-----------|
| **None** | Stealth Playwright scans 24 broker sites, sends CCPA emails via SMTP | Free | Default |
| **HIBP** | Unlocks paste search and removes rate limits on breach checks | $3.50/mo | No — free tier works for basic breach checks |
| **2captcha** | Solves reCAPTCHA v2 and hCaptcha on broker opt-out forms | ~$3/1000 solves | No — most sites don't require CAPTCHA for search |
| **Capsolver** | Alternative CAPTCHA provider, same capabilities as 2captcha | ~$2-3/1000 solves | No — alternative to 2captcha |
| **Residential Proxy** | Bypasses Cloudflare bot detection on ~13 protected sites | $8-15/GB | No — the 11 unprotected sites cover the major brokers |

### What works without any API keys

- Scans **Whitepages, Spokeo, IDCrawl, Intelius, ThatsThem, Radaris, BeenVerified** and more
- Sends **CCPA/GDPR deletion emails** to all 78 brokers via your SMTP
- **Automated form opt-outs** via Playwright on sites without CAPTCHA
- **Post-removal verification** rescans to confirm deletion
- **Privacy score**, PDF reports, Signal/webhook notifications

### Sites blocked without residential proxy

FastPeopleSearch, TruePeopleSearch, PeopleFinders, Nuwber, USPhoneBook, CyberBackgroundChecks, SearchPeopleFree, FamilyTreeNow, AdvancedBackgroundChecks, SmartBackgroundChecks, VoterRecords, CocoFinder, and USA People Search use Cloudflare bot protection that returns 403 to datacenter IPs. A residential proxy ($8-15/GB) would unlock these.

---

## Broker Database

78 data brokers with documented opt-out methods:

| Category | Count | Examples |
|----------|-------|---------|
| People Search | 35 | Whitepages, Spokeo, BeenVerified, Intelius, TruePeopleSearch |
| Data Aggregators | 18 | Acxiom, LexisNexis, Oracle Data Cloud, Epsilon |
| Marketing/Advertising | 12 | LiveRamp, Datalogix, BlueKai |
| Background Check | 8 | Checkpeople, InstantCheckmate, PeopleFinders |
| Other | 5 | Radaris, Nuwber, FastPeopleSearch |

Each broker YAML includes:
- Opt-out method (email, form, or manual)
- Legal template selection (CCPA, GDPR)
- Form selectors for Playwright automation
- Verification timeline (7-30 days expected)
- Reappearance detection interval (90-180 days)

### Adding a Broker

```yaml
slug: example-broker
name: Example Broker
url: https://example-broker.com
category: people_search
priority: medium
data_types: [name, phone, email, address]

opt_out:
  methods:
    - type: email
      address: privacy@example-broker.com
      template: ccpa_deletion_request
    - type: form
      url: https://example-broker.com/opt-out
      steps:
        - action: goto
          url: https://example-broker.com/opt-out
        - action: fill
          selector: "input[name=email]"
          field: email
        - action: click
          selector: "button[type=submit]"
        - action: screenshot
          name: submission_proof

  verification:
    type: check_listing
    expected_days: 14

  reappearance:
    frequency_days: 90
```

Validate with `privacy-toolkit brokers validate`.

---

## Security

### Authentication
- **bcrypt password hashing** with per-session random tokens (`secrets.token_urlsafe`)
- **24-hour session expiry** with automatic invalidation
- **API key auth** (optional) via `X-API-Key` header with timing-safe comparison
- **OAuth2 Proxy** (production) — GitHub OAuth via oauth2-proxy for reverse proxy deployments

### Request Protection
- **CSRF** — double-submit cookie pattern (OWASP), `SameSite=Strict`, validated on all POST requests
- **Security headers** — HSTS, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, Referrer-Policy, Permissions-Policy
- **Path traversal prevention** — rejects `..`, `/`, `\`, null bytes in all user-supplied file paths
- **Sandboxed Jinja2** — auto-escaping enabled, SRI hashes on all CDN scripts

### Data Protection
- **No plaintext secrets** — all credentials use `${ENV_VAR}` resolution
- **SQLite WAL mode** — concurrent read access without locking
- **Audit logging** — every action recorded with timestamp, profile, and success/failure

---

## Architecture

```
privacy-toolkit/
├── src/
│   ├── app.py                  # FastAPI web application + HTMX routes
│   ├── cli.py                  # Click CLI with Rich progress bars
│   ├── config.py               # YAML config, env var resolution, dataclasses
│   ├── db.py                   # SQLite with WAL, dedup index, score history
│   ├── auth.py                 # bcrypt auth, session store, middleware
│   ├── csrf.py                 # CSRF double-submit cookie middleware
│   ├── models.py               # Pydantic data models
│   ├── tasks.py                # Background task manager (ThreadPoolExecutor)
│   ├── scheduler.py            # APScheduler + cron scheduling
│   ├── scoring.py              # Privacy score calculator with trending
│   ├── notifications.py        # Signal + webhook multi-channel dispatch
│   ├── captcha_solver.py       # 2captcha + capsolver integration
│   ├── scanners/               # 7 scanner implementations
│   │   ├── hibp_scanner.py
│   │   ├── holehe_scanner.py
│   │   ├── sherlock_scanner.py
│   │   ├── maigret_scanner.py
│   │   ├── phoneinfoga_scanner.py
│   │   └── people_search_scanner.py  # 25+ sites, fallback selectors
│   ├── removers/               # Email + form removal engines
│   │   ├── email_remover.py    # SMTP with response classification
│   │   └── form_remover.py     # Playwright with CAPTCHA support
│   ├── reporting/              # PDF, CSV, JSON, HTML export
│   └── web/                    # Jinja2 templates + Tailwind CSS
├── brokers/                    # 78 broker YAML definitions
├── guides/                     # 40 service deletion guides
├── templates/                  # Legal email templates (CCPA, GDPR)
├── config/                     # Configuration files
├── tests/                      # 256 pytest tests
├── .github/workflows/          # CI, security scanning, auto-deploy
├── Dockerfile
├── docker-compose.yml
└── install.sh
```

---

## CI/CD Pipeline

### Continuous Integration

Every push triggers 4 parallel jobs:

| Job | What It Checks |
|-----|---------------|
| **test** | Ruff linting, 256 pytest tests, syntax validation |
| **validate-brokers** | YAML schema validation for all 78 broker definitions |
| **validate-guides** | YAML schema validation for all 40 deletion guides |
| **security-sast** | Semgrep (OWASP Top 10 + Python rules) + Bandit (HIGH severity gate) |

### Scheduled Security

- **Weekly** (Sunday 2 AM) — Semgrep + Bandit scan with auto-remediation via Claude CLI
- **Monthly** (1st Saturday 3 AM) — Shannon penetration test (exploitation-grade)
- Failed fixes are automatically reverted; successful fixes create a PR

### Auto-Deploy

On merge to `main`: pull → build → health check → rollback on failure → Signal notification.

---

## Testing

```bash
# Run full suite
privacy-toolkit doctor deps && pytest tests/ -x -q

# Run specific test files
pytest tests/test_db.py -v
pytest tests/test_improvements.py -v
pytest tests/test_url_discovery.py -v
```

**256 tests** covering:
- Database operations, dedup, score history, schema migrations
- Authentication (bcrypt, sessions, expiry, CSRF)
- Scanner integrations (mocked external APIs)
- Removal request lifecycle and state machine
- URL discovery and verification
- Proxy, UA rotation, CAPTCHA solver configuration
- PDF/CSV/JSON/HTML report generation
- Notification dispatch (Signal + webhook)
- Web application routes and middleware
- Security (path traversal, input validation, template escaping)

---

## Roadmap

Planned improvements based on competitive analysis against enterprise tools:

- [ ] **Re-listing auto-resubmission** — automatically resend removal requests when brokers re-add data (like Incogni's 60-day cycle)
- [ ] **Broker compliance scoring** — track response rates per broker to prioritize targets (like Incogni's severity ratings)
- [ ] **REST API** — full programmatic access for integration with external tools and automation platforms
- [ ] **Automated response routing** — parse broker email replies and auto-transition removal status
- [ ] **Before/after screenshot evidence** — capture listing screenshots during scan and verification for removal proof (like Optery)
- [ ] **Compliance report generator** — produce legal-ready PDF documenting all requests, responses, and timelines
- [ ] **Notification digest** — periodic summary of removals confirmed, scores changed, and new exposures found
- [ ] **Threat-model prioritization** — weight removal urgency by data sensitivity and user risk profile (like Kanary)
- [ ] **Search engine cache removal** — request removal of cached listings from Google, Bing after broker deletion confirmed
- [ ] **Data visualization** — score history charts, exposure heatmaps, and broker status breakdowns on the dashboard
- [ ] **Multi-profile family dashboard** — aggregate household view with per-person score tracking
- [ ] **Broker database auto-update** — health check system to detect broken opt-out URLs and stale CSS selectors

---

## Comparison

| Feature | Privacy Toolkit | DeleteMe | Incogni | Optery | EasyOptOuts |
|---------|:-:|:-:|:-:|:-:|:-:|
| Price | Free | $129/yr | $78/yr | $249/yr | $20/yr |
| Data brokers | 78 | 750+ | 420+ | 955+ | 160+ |
| Email removals | Yes | Yes | Yes | Yes | No |
| Form removals | Yes | Manual | Yes | Yes | Yes |
| CAPTCHA solving | Yes | Yes | Yes | Yes | No |
| Breach monitoring | Yes (HIBP) | No | No | No | No |
| Username OSINT | Yes | No | No | No | No |
| Post-removal verification | Yes | Yes | Yes | Yes | Yes |
| Privacy score | Yes | No | No | Yes | No |
| PDF reports | Yes | Yes | Yes | Yes | No |
| Webhook notifications | Yes | No | No | No | No |
| Open source | Yes | No | No | No | No |
| Self-hosted | Yes | No | No | No | No |
| API access | Partial | No | No | No | No |

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Add tests for new functionality
4. Run `pytest tests/ -x -q && ruff check src/ tests/`
5. Submit a pull request

Broker YAML contributions are especially welcome — see [Adding a Broker](#adding-a-broker).

---

## License

[MIT License](LICENSE) — free for personal and commercial use.
