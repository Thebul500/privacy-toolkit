# Privacy Toolkit

[![CI](https://github.com/Thebul500/privacy-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/Thebul500/privacy-toolkit/actions/workflows/ci.yml)

Automated personal data discovery and removal across 78 data brokers and people-search sites. Scans for your digital footprint, generates legally-compliant CCPA/GDPR deletion requests, and tracks removal progress over time.

## Features

- **Multi-vector discovery** — scan emails, usernames, phone numbers, and addresses across data brokers, breach databases, and social platforms
- **Account discovery** — find accounts linked to your email, phone, or username with interactive removal guidance
- **Breach exposure reports** — aggregate breach data across all your emails with risk assessment (HIGH/MEDIUM/LOW)
- **78 pre-configured data brokers** — Whitepages, Spokeo, BeenVerified, Intelius, and 74 more with documented opt-out methods
- **40 service deletion guides** — step-by-step account deletion instructions for Facebook, Google, LinkedIn, Steam, and more
- **Automated removal requests** — SMTP email with legal templates (CCPA, GDPR, CPRA, VCDPA) and Playwright-based form submissions
- **Removal tracking** — full lifecycle management: pending, submitted, confirmed, reappeared
- **Periodic re-scanning** — cron-based scheduling to detect re-listed data (configurable intervals)
- **Web dashboard** — FastAPI + HTMX interface with account discovery, scan management, and audit log
- **CLI with progress bars** — full-featured Click CLI with Rich progress indicators
- **CSV and HTML export** — export findings and removal status in multiple formats
- **Signal notifications** — scan completion alerts via Signal REST API
- **Environment variable secrets** — `${ENV_VAR}` syntax and auto-fallback for SMTP, HIBP, Signal credentials
- **177 tests** — pytest suite covering db, config, models, scanners, notifications, security, and reporting

## Scanners

| Scanner | What it finds | Source |
|---------|---------------|--------|
| HaveIBeenPwned | Data breaches and pastes | HIBP API |
| Holehe | Email registrations across services | holehe |
| Sherlock | Username presence on 300+ sites | sherlock-project |
| Maigret | Advanced username OSINT | maigret |
| PhoneInfoga | Phone number intelligence | phoneinfoga binary |
| People Search | Data broker listings | Playwright + headless Chromium |
| SpiderFoot | Full OSINT framework | Docker container |

## Quick Start

### Local Install

```bash
git clone https://github.com/Thebul500/privacy-toolkit.git
cd privacy-toolkit
bash install.sh
```

The installer creates a virtualenv, installs dependencies, downloads PhoneInfoga, installs Playwright Chromium, and creates a `privacy-toolkit` CLI entry point.

### Docker

```bash
# Copy and fill in OAuth secrets
cp .env.example .env
# Edit .env with your GitHub OAuth App credentials

docker-compose up -d
# Web UI at http://localhost:8384 (direct)
# OAuth proxy at http://localhost:4180 (authenticated)
```

### Configuration

```bash
cp config/config.yaml.example config/config.yaml
```

Edit `config/config.yaml` with your settings:

- **SMTP** — Gmail app password for sending deletion request emails (or set `SMTP_PASSWORD` env var)
- **HIBP API key** — optional, for breach detection (or set `HIBP_API_KEY` env var)
- **Signal** — optional, for scan completion notifications (or set `SIGNAL_SENDER` env var)
- **Browser** — headless mode, timeouts, rate limiting, screenshot preferences

Secrets support three formats:
```yaml
password: "literal-value"         # Used as-is
password: "${SMTP_PASSWORD}"      # Resolved from env var
password: ""                      # Auto-fallback to SMTP_PASSWORD env var
```

## Usage

### Check Dependencies

```bash
privacy-toolkit doctor
```

Reports status of all 12 dependencies: Python, Playwright, Holehe, Sherlock, Maigret, PhoneInfoga, SpiderFoot, SMTP, HIBP API, Signal, Database, Brokers.

### Create a Profile

```bash
privacy-toolkit profile create myname
# Interactive prompts for name, emails, phones, usernames, addresses
```

### Run Scans

```bash
# Full scan (all scanners) with progress bar
privacy-toolkit scan full -p myname

# Individual scanners
privacy-toolkit scan email user@example.com
privacy-toolkit scan username johndoe
privacy-toolkit scan phone +15551234567
privacy-toolkit scan people "John Doe" --type name
```

### Discover Accounts

```bash
# Find accounts linked to an email (Holehe + HIBP)
privacy-toolkit accounts find-by-email user@example.com

# Find accounts linked to a phone number
privacy-toolkit accounts find-by-phone +15551234567

# Find accounts by username (Sherlock + Maigret, deduplicated)
privacy-toolkit accounts find-by-username johndoe

# Breach exposure report across all profile emails
privacy-toolkit accounts exposure-report -p myname
```

Each command shows results in a Rich table and offers interactive removal guidance with links to deletion guides.

### Submit Removal Requests

```bash
# Preview what would be sent
privacy-toolkit remove email-request -p myname --dry-run

# Send CCPA/GDPR deletion emails to all brokers with findings
privacy-toolkit remove email-request -p myname

# Target a specific broker
privacy-toolkit remove email-request -p myname -b whitepages

# Automated form submission (Playwright)
privacy-toolkit remove form-request -p myname -b spokeo

# Preview form steps without submitting
privacy-toolkit remove form-request -p myname -b spokeo --dry-run

# Show manual removal instructions
privacy-toolkit remove manual -p myname
```

### Track Removals

```bash
privacy-toolkit track status -p myname     # All removal requests
privacy-toolkit track pending -p myname    # Due for recheck
privacy-toolkit track history -p myname    # Scan history
privacy-toolkit track confirm 42           # Mark removal confirmed
privacy-toolkit track reappeared 42        # Mark re-listed
```

### Schedule Re-scans

```bash
privacy-toolkit schedule enable -p myname   # Install cron jobs
privacy-toolkit schedule status             # Show scheduled jobs
privacy-toolkit schedule disable            # Remove cron jobs
```

Default schedule: full re-scan every Sunday at 3 AM, pending recheck daily at 9 AM.

### Reports

```bash
privacy-toolkit report -p myname                        # Terminal table
privacy-toolkit report -p myname -f json -o report.json # JSON
privacy-toolkit report -p myname -f csv -o report.csv   # CSV
privacy-toolkit report -p myname -f html -o report.html # HTML
privacy-toolkit report -p myname -f csv -t removals     # Removal status CSV
```

### Validate Brokers

```bash
privacy-toolkit brokers                    # List all 78
privacy-toolkit brokers -P critical        # Filter by priority
privacy-toolkit brokers validate           # Validate all YAML schemas
```

## Web Dashboard

The web UI runs on port 8080 (or 8384 via Docker) and provides:

- **Dashboard** — stats overview, recent activity, active background tasks
- **Profiles** — create and manage identity profiles
- **Scans** — trigger scans with live status updates
- **Accounts** — discover linked accounts by email/phone/username with risk assessment
- **Removals** — track all requests, mark confirmed/reappeared, submit new batches
- **Brokers** — browse the 78 configured brokers by priority
- **Activity** — audit log of all actions

## Security

### Authentication

**OAuth2 Proxy** (production) — GitHub OAuth login via [oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/), restricted to allowed GitHub users. Sits in front of the app as a reverse proxy on port 4180.

Setup:
1. Create a GitHub OAuth App: **Settings > Developer Settings > OAuth Apps > New**
   - Homepage URL: `https://privacy.example.com`
   - Callback URL: `https://privacy.example.com/oauth2/callback`
2. Copy credentials to `.env` (see `.env.example`)
3. Generate cookie secret: `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`
4. Update Nginx Proxy Manager: forward `privacy.example.com` to `oauth2-proxy:4180` instead of `privacy-toolkit:8384`
5. Remove any existing basic auth access lists

**API Key** (optional) — set `PRIVACY_TOOLKIT_API_KEY` env var to require `X-API-Key` header on all requests. The `/api/health` endpoint is always public.

### CSRF Protection

Double-submit cookie pattern (OWASP). `SameSite=Strict` cookie, validated on all state-changing POST requests. HTMX requests include the token via `X-CSRF-Token` header automatically.

### Security Headers

All responses include:
- `X-Content-Type-Options: nosniff` — prevents MIME-type sniffing
- `X-Frame-Options: DENY` — prevents clickjacking
- `Referrer-Policy: strict-origin-when-cross-origin` — limits referrer leakage
- `Permissions-Policy: camera=(), microphone=(), geolocation=()` — disables unused browser APIs
- `X-XSS-Protection: 1; mode=block` — legacy XSS filter
- `Strict-Transport-Security: max-age=63072000; includeSubDomains` — HSTS (HTTPS only)

### Input Validation

Path traversal prevention on all file operations. Null bytes, `..`, `/`, and `\` are rejected in profile names and broker slugs via `validate_safe_name()`.

### Template Security

Jinja2 auto-escaping enabled globally. CDN scripts pinned with Subresource Integrity (SRI) hashes to prevent CDN tampering.

### TLS

Let's Encrypt certificates via Nginx Proxy Manager with forced HTTPS redirect and HTTP/2.

### Secrets Management

All secrets use `${ENV_VAR}` resolution in config files — no plaintext secrets committed. OAuth credentials stored in `.env` (gitignored).

## Service Deletion Guides

40 YAML guides in `guides/` with step-by-step account deletion instructions:

| Category | Services |
|----------|----------|
| Social | Facebook, Instagram, Twitter/X, LinkedIn, TikTok, Snapchat, Reddit, Pinterest, Tumblr, Discord |
| Email | Gmail, Outlook, Yahoo, WhatsApp |
| Cloud | Dropbox, iCloud |
| Shopping | Amazon, eBay, Etsy, Walmart |
| Streaming | Netflix, Spotify, Hulu, Disney+, Twitch, YouTube |
| Gaming | Steam, Epic Games, PlayStation, Xbox |
| Finance | PayPal, Venmo, Cash App |
| Productivity | Slack, Zoom, Adobe, Canva |
| Developer | GitHub, StackOverflow, npm |

## Email Templates

Three Jinja2 legal templates in `templates/`:

| Template | Purpose |
|----------|---------|
| `ccpa_deletion_request.j2` | Formal deletion request citing CCPA, CPRA, VCDPA, CPA, CTDPA, TDPSA, OCPA, FCRA |
| `gdpr_deletion_request.j2` | EU GDPR Article 17 right to erasure |
| `follow_up_request.j2` | Follow-up for non-responsive brokers |

## Adding Brokers

Create a YAML file in `brokers/`:

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
      subject: "Data Deletion Request"

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
          name: example_submission

  verification:
    type: check_listing
    expected_days: 14

  reappearance:
    frequency_days: 90

privacy_policy_url: https://example-broker.com/privacy
```

Validate with `privacy-toolkit brokers validate`.

## Project Structure

```
privacy-toolkit/
├── src/
│   ├── app.py                 # FastAPI web application
│   ├── cli.py                 # Click CLI with Rich progress bars
│   ├── config.py              # YAML config loader + env var support
│   ├── db.py                  # SQLite database layer
│   ├── models.py              # Pydantic data models
│   ├── tasks.py               # Background task manager
│   ├── scheduler.py           # Cron + APScheduler
│   ├── notifications.py       # Signal API integration
│   ├── scanners/              # 8 scanner implementations
│   ├── removers/              # Email, form, and manual removal
│   ├── reporting/             # Terminal, JSON, CSV, HTML export
│   └── web/                   # Jinja2 templates + static assets
├── brokers/                   # 78 broker YAML definitions
├── guides/                    # 40 service deletion guides
├── templates/                 # Legal email templates
├── config/                    # Configuration files
├── tests/                     # 177 pytest tests
├── data/                      # SQLite DB, logs, screenshots
├── bin/                       # PhoneInfoga binary (not included, see install.sh)
├── .github/workflows/
│   ├── ci.yml               # CI: lint, test, SAST (Semgrep + Bandit)
│   ├── security.yml         # Weekly scheduled security scan
│   └── deploy.yml           # Auto-deploy on merge to main
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── install.sh
```

## CI/CD Pipeline

### Continuous Integration

Every push and PR triggers:
- **Ruff** — Python linting (E, F, W rules)
- **pytest** — 177 tests covering db, config, models, scanners, notifications, security, and reporting
- **Syntax check** — compile-time validation of all Python source files
- **Broker validation** — YAML schema validation for all 78 broker definitions
- **Guide validation** — YAML schema validation for all 40 service deletion guides
- **Semgrep SAST** — static analysis with `p/python` and `p/owasp-top-ten` rulesets
- **Bandit** — Python security linter (blocks on HIGH severity findings)

### Weekly Security Scan

Runs every Sunday at 2 AM CST via cron (on-host) and GitHub Actions:
1. **Semgrep** scans `src/` with `auto`, `p/python`, `p/owasp-top-ten` rulesets
2. **Bandit** scans for Python-specific security issues
3. **Claude CLI** auto-remediates findings (Sonnet 4.6, $10 budget cap)
4. Tests run after each fix — failed fixes are reverted and logged
5. Creates a PR with all successful fixes
6. Sends a Signal notification with scan summary

### Monthly Penetration Testing

First Saturday of each month at 3 AM CST:
1. **Shannon** runs a full exploitation-grade pentest (~$60, 1-2 hours)
2. Results parsed from Temporal deliverables
3. Optionally triggers auto-remediation pipeline
4. Signal notification with findings summary

### Auto-Deploy

On merge to `main`:
1. Poller detects new commits every 5 minutes
2. `git pull` + `docker compose build --no-cache` + `docker compose up -d`
3. Health check: 6 retries at 10s intervals on `/api/health`
4. On failure: automatic rollback to previous commit
5. Signal notification for success or failure

### Manual Commands

```bash
# Run security scan (dry run — scan only, no fixes)
bash scripts/security-audit.sh --dry-run

# Run full scan with auto-remediation
bash scripts/security-audit.sh

# Run Shannon pentest (expensive)
bash scripts/shannon-pentest.sh

# Parse existing Shannon results without re-scanning
bash scripts/shannon-pentest.sh --skip-scan --remediate

# Manual deploy
bash scripts/deploy-privacy-toolkit.sh

# Force redeploy even if already up-to-date
bash scripts/deploy-privacy-toolkit.sh --force
```

## Requirements

- Python 3.12+
- Chromium (installed automatically by Playwright)
- Docker (optional, for SpiderFoot scanner and containerized deployment)
- SMTP credentials (for sending deletion request emails)

## License

Private repository. All rights reserved.
