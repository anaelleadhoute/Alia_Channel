# AL.IA Channel

Automated media pipeline for the AL.IA Community — delivers Israeli news and social rights tips to francophone and Russian-speaking olim via WhatsApp and Instagram.

## What it does

1. Scrapes French and Russian RSS news sources every few hours
2. Scrapes Kol Zchut (Israeli social rights guide) weekly
3. Processes each article with Claude Haiku — generates titles, summaries, WhatsApp CTAs, Instagram captions, relevance scores, and categories in both FR and RU in parallel
4. Presents content in a validation dashboard for human review (approve / reject / edit)
5. Publishes approved content to WhatsApp (FR + RU groups) and Instagram

## Architecture

```
nginx (HTTPS) ──► FastAPI backend  ──► SQLite
                      │
                      ├── Scrapers (RSS + Kol Zchut)
                      ├── AI Processor (Claude Haiku)
                      └── Publisher (Whapi.Cloud + Meta API)

n8n ──► scheduled workflows (scrape / process / publish)
dashboard ──► validation UI (approve / reject / edit)
```

## Stack

| Layer | Tech |
|---|---|
| Server | Hetzner VPS CX23, Falkenstein |
| Reverse proxy | nginx + Let's Encrypt (Certbot) |
| Backend | FastAPI (Python) |
| Database | SQLite (aiosqlite) |
| AI | Claude Haiku (Anthropic) |
| Orchestration | n8n |
| WhatsApp | Whapi.Cloud |
| Instagram | Meta Graph API |
| Infra | Docker Compose |

## API endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/scrape/news` | Fetch RSS + AI-process new articles |
| POST | `/api/scrape/tips` | Scrape Kol Zchut + AI-process tip |
| POST | `/api/scrape/tips/manual` | Receive tip from local Mac scraper |
| POST | `/api/scrape/cleanup` | Delete old sent/rejected articles |
| POST | `/api/scrape/reset-ai` | Reprocess all articles through AI |
| GET | `/api/articles` | List articles (filterable by status/language) |
| GET | `/api/tips` | List tips |
| POST | `/api/publish/article/{id}` | Publish article to channel |

## Services

| URL | Service |
|---|---|
| https://alia-channel.com | Main domain |
| https://alia-channel.com/api | FastAPI backend |
| https://alia-channel.com/n8n/ | n8n orchestration UI |

## Setup

### Prerequisites
- Docker + Docker Compose
- Domain pointed to server IP
- Anthropic API key
- Whapi.Cloud account (for WhatsApp)
- Meta developer account (for Instagram)

### Environment variables

Copy `.env.template` to `.env` and fill in:

```
ANTHROPIC_API_KEY=
WHAPI_TOKEN=
META_ACCESS_TOKEN=
META_INSTAGRAM_ACCOUNT_ID=
N8N_USER=
N8N_PASSWORD=
N8N_ENCRYPTION_KEY=
DOMAIN=alia-channel.com
```

### Deploy

```bash
# First time — run on the VPS
bash scripts/setup_server.sh
bash scripts/init_https.sh

# Start all services
docker compose up -d

# Pull latest changes
git pull && docker compose restart backend
```

### Local Kol Zchut scraper (runs on Mac)

```bash
python scripts/kolzchut_local.py
```

Fetches the weekly Kol Zchut page and sends it to `/api/scrape/tips/manual`.

## Phases

- [x] Phase 1 — Infrastructure (VPS, Docker, nginx, HTTPS, n8n)
- [x] Phase 2 — Scrapers (RSS FR/RU, Kol Zchut, deduplication)
- [x] Phase 3 — AI Processing (Claude Haiku, FR + RU in parallel)
- [ ] Phase 4 — Image generation (Pillow)
- [ ] Phase 5 — Validation dashboard
- [ ] Phase 6 — WhatsApp publishing (Whapi.Cloud)
- [ ] Phase 7 — Instagram publishing (Meta Graph API)
- [ ] Phase 8 — n8n workflows
- [ ] Phase 9 — Monitoring + alerts
