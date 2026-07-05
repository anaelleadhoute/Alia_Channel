# AL.IA Channel

Automated media pipeline for the AL.IA Community — delivers Israeli news, social rights tips, deals, and weekly FAQs to francophone and Russian-speaking olim via WhatsApp.

## What it does

1. **Daily news digest** — scrapes 5 Israeli news sources (Times of Israel, Jerusalem Post, Ynet, Israel Hayom, Walla, i24news FR/RU), scores relevance with Claude, generates a summarized digest in FR + RU
2. **Kol Zchut tips** — weekly social rights tips scraped from kolzchut.org.il, processed into practical FR + RU messages; deduplicates against last 8 weeks
3. **Weekly FAQ** — Claude generates the most frequently asked olim question of the week with a full answer in FR + RU; deduplicates against last 8 weeks
4. **Telegram deals** — scrapes 4 Telegram channels (supermarket, electronics, flights, hotels), uses Claude Vision to score relevance and detect audience (FR / RU / both), keeps top deal per channel
5. **WhatsApp publishing** — sends all content to FR and RU groups via Whapi.Cloud; audience-aware for deals (flights to Paris → FR only, flights to Moscow → RU only)

## Architecture

```
nginx (HTTPS) ──► FastAPI backend ──► SQLite
                      │
                      ├── Scrapers (RSS × 5 + Kol Zchut + Telegram × 4)
                      ├── AI Processor (Claude Haiku — FR + RU in parallel)
                      ├── Digest Processor (daily summary)
                      ├── FAQ Processor (weekly)
                      └── Publisher (Whapi.Cloud)

Local Mac ──► scripts/kolzchut_local.py ──► POST /api/scrape/tips/manual
```

## Stack

| Layer | Tech |
|---|---|
| Server | Hetzner VPS CX23, Falkenstein |
| Reverse proxy | nginx + Let's Encrypt (Certbot) |
| Backend | FastAPI (Python) |
| Database | SQLite (aiosqlite) |
| AI | Claude Haiku (Anthropic) |
| WhatsApp | Whapi.Cloud |
| Infra | Docker Compose |

## API endpoints

### Scrape
| Method | Path | Description |
|---|---|---|
| POST | `/api/scrape/news` | Fetch RSS sources + AI-process new articles |
| POST | `/api/scrape/tips` | Scrape Kol Zchut + AI-process tip |
| POST | `/api/scrape/tips/manual` | Receive tip from local Mac scraper |
| POST | `/api/scrape/deals` | Scrape Telegram deal channels |
| POST | `/api/scrape/cleanup` | Delete old sent/rejected content |
| POST | `/api/scrape/reset-ai` | Reprocess all articles through AI |

### Content
| Method | Path | Description |
|---|---|---|
| GET | `/api/articles` | List articles |
| GET | `/api/tips` | List tips |
| GET | `/api/deals` | List deals |
| GET | `/api/faqs` | List FAQs |
| GET | `/api/digests` | List digests |
| POST | `/api/faqs/generate` | Generate weekly FAQ (FR + RU) |
| POST | `/api/digests/generate` | Generate daily news digest (FR + RU) |

### Publish
| Method | Path | Description |
|---|---|---|
| POST | `/api/publish/article/{id}` | Publish article to WhatsApp |
| POST | `/api/publish/tip/{id}` | Publish tip to WhatsApp |
| POST | `/api/publish/deal/{id}` | Publish deal (audience-aware) |
| POST | `/api/publish/faq/{id}` | Publish FAQ to WhatsApp |
| POST | `/api/publish/digest/{id}` | Publish digest to WhatsApp |
| POST | `/api/publish/digest/latest` | Publish most recent digest |

## Daily workflow

```bash
# 1. Scrape fresh news
curl -X POST https://alia-channel.com/api/scrape/news

# 2. Generate digest
curl -X POST https://alia-channel.com/api/digests/generate

# 3. Publish to WhatsApp
curl -X POST https://alia-channel.com/api/publish/digest/latest
```

## Weekly workflow

```bash
# Run on Mac (Kol Zchut blocked on server)
python scripts/kolzchut_local.py

# Generate FAQ
curl -X POST https://alia-channel.com/api/faqs/generate

# Publish tip + FAQ
curl -X POST https://alia-channel.com/api/publish/tip/{id}
curl -X POST https://alia-channel.com/api/publish/faq/{id}
```

## News sources

| Source | Language | Status |
|---|---|---|
| i24news FR | FR | ✅ |
| i24news RU | RU | ✅ |
| JForum | FR | ✅ |
| Times of Israel | EN → FR+RU | ✅ |
| Jerusalem Post | EN → FR+RU | ✅ |
| Ynet | HE → FR+RU | ✅ |
| Israel Hayom | EN → FR+RU | ✅ |
| Walla News | HE → FR+RU | ✅ |

## Telegram deal channels

| Channel | Category |
|---|---|
| shufersaloffocial | Supermarket |
| payngoil | Electronics |
| SecretFlights | Flights |
| hotelscoil | Hotels |

## Services

| URL | Service |
|---|---|
| https://alia-channel.com | Main domain |
| https://alia-channel.com/api | FastAPI backend |
| https://alia-channel.com/docs | Swagger UI |

## Environment variables

Copy `.env.template` to `.env` and fill in:

```
ANTHROPIC_API_KEY=
WHAPI_TOKEN=
WHAPI_GROUP_FR=
WHAPI_GROUP_RU=
DOMAIN=alia-channel.com
```

## Deploy

```bash
# First time
bash scripts/setup_server.sh
bash scripts/init_https.sh

# Start
docker compose up -d

# Update
git pull && docker compose restart backend
```

## Phases

- [x] Phase 1 — Infrastructure (VPS, Docker, nginx, HTTPS)
- [x] Phase 2 — Scrapers (RSS, Kol Zchut, Telegram deals)
- [x] Phase 3 — AI Processing (Claude Haiku, FR + RU in parallel, relevance scoring)
- [x] Phase 4 — WhatsApp publishing (Whapi.Cloud, audience-aware)
- [x] Phase 5 — Weekly FAQ generator (deduplication over 8 weeks)
- [x] Phase 6 — Daily news digest (published_at filtering, score threshold)
- [ ] Phase 7 — Validation dashboard
- [ ] Phase 8 — Image generation (Pillow)
- [ ] Phase 9 — Instagram publishing (Meta Graph API)
- [ ] Phase 10 — Automated scheduling (n8n or cron)
- [ ] Phase 11 — Monitoring + alerts
