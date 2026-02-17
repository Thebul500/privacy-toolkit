# Privacy Toolkit

Automated personal data discovery and removal across 78 data brokers and people-search sites. Scans for your digital footprint, generates legally-compliant CCPA/GDPR deletion requests, and tracks removal progress over time.

## Features

- **Multi-vector discovery** — scan emails, usernames, phone numbers, and addresses across data brokers, breach databases, and social platforms
- **78 pre-configured data brokers** — Whitepages, Spokeo, BeenVerified, Intelius, and 74 more with documented opt-out methods
- **Automated removal requests** — SMTP email with legal templates (CCPA, GDPR, CPRA, VCDPA) and Playwright-based form submissions
- **Removal tracking** — full lifecycle management: pending, submitted, confirmed, reappeared
- **Periodic re-scanning** — cron-based scheduling to detect re-listed data (configurable intervals)
- **Web dashboard** — FastAPI + HTMX interface with real-time task status, profile management, and audit log
- **CLI** — full-featured Click CLI for scripting and automation
- **Signal notifications** — scan completion alerts via Signal REST API

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
docker-compose up -d
# Web UI at http://localhost:8384
```

### Configuration

```bash
cp config/config.yaml.example config/config.yaml
```

Edit `config/config.yaml` with your settings:

- **SMTP** — Gmail app password for sending deletion request emails
- **HIBP API key** — optional, for breach detection ([get one here](https://haveibeenpwned.com/API/Key))
- **Signal** — optional, for scan completion notifications
- **Browser** — headless mode, timeouts, screenshot preferences

## Usage

### Create a Profile

```bash
privacy-toolkit profile create myname
# Interactive prompts for name, emails, phones, usernames, addresses
```

### Run Scans

```bash
# Full scan (all scanners)
privacy-toolkit scan full -p myname

# Individual scanners
privacy-toolkit scan email user@example.com
privacy-toolkit scan username johndoe
privacy-toolkit scan phone +15551234567
privacy-toolkit scan people "John Doe" --type name
```

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
privacy-toolkit report -p myname              # Terminal table
privacy-toolkit report -p myname -f json      # JSON export
privacy-toolkit report -p myname -f json -o results.json
```

### Browse Brokers

```bash
privacy-toolkit brokers                       # List all 78
privacy-toolkit brokers -P critical           # Filter by priority
```

## Web Dashboard

The web UI runs on port 8080 (or 8384 via Docker) and provides:

- **Dashboard** — stats overview, recent activity, active background tasks
- **Profiles** — create and manage identity profiles
- **Scans** — trigger scans with live status updates
- **Removals** — track all requests, mark confirmed/reappeared, submit new batches
- **Brokers** — browse the 78 configured brokers by priority
- **Activity** — audit log of all actions

## Email Templates

Three Jinja2 legal templates in `templates/`:

| Template | Purpose |
|----------|---------|
| `ccpa_deletion_request.j2` | Formal deletion request citing CCPA, CPRA, VCDPA, CPA, CTDPA, TDPSA, OCPA, FCRA |
| `gdpr_deletion_request.j2` | EU GDPR Article 17 right to erasure |
| `follow_up_request.j2` | Follow-up for non-responsive brokers |

Emails include evidence (found listing URLs), identifying information, legal citations, and FTC/state AG cc notice.

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

## Project Structure

```
privacy-toolkit/
├── src/
│   ├── app.py                 # FastAPI web application
│   ├── cli.py                 # Click CLI
│   ├── config.py              # YAML configuration loader
│   ├── db.py                  # SQLite database layer
│   ├── models.py              # Pydantic data models
│   ├── tasks.py               # Background task manager
│   ├── scheduler.py           # Cron + APScheduler
│   ├── notifications.py       # Signal API integration
│   ├── scanners/              # 8 scanner implementations
│   ├── removers/              # Email, form, and manual removal
│   ├── reporting/             # Terminal tables + JSON export
│   └── web/                   # Jinja2 templates + static assets
├── brokers/                   # 78 broker YAML definitions
├── templates/                 # Legal email templates
├── config/                    # Configuration files
├── data/                      # SQLite DB, logs, screenshots
├── bin/                       # PhoneInfoga binary
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── install.sh
```

## Requirements

- Python 3.12+
- Chromium (installed automatically by Playwright)
- Docker (optional, for SpiderFoot scanner and containerized deployment)
- SMTP credentials (for sending deletion request emails)

## License

Private repository. All rights reserved.
