# AL.IA Channel

Automated media pipeline for the AL.IA Community — delivers Israeli news, social rights tips, deals, kids events, prestataire highlights, and weekly FAQs to French and Russian-speaking olim via WhatsApp.

## What it does

1. **Daily news digest** — scrapes Jerusalem Post (RSS), scores relevance with Claude, generates a summarized digest in FR + RU
2. **Weekly Guide (tip)** — Kol Zchut content scraped locally on Mac and sent to server; processed into practical FR + RU messages
3. **Weekly Droits (rights)** — rights content from Kol Zchut, same local-scrape-then-send flow
4. **Weekly Prestataire** — rotating spotlight on a French/Russian-speaking service provider in Israel
5. **Weekly Kids Events** — local scraper finds children's events, server generates FR + RU summary
6. **Weekly Médecins** — spotlight on a French/Russian-speaking doctor in Israel
7. **Deals** — scrapes Telegram channels (supermarket, electronics, flights, hotels), uses Claude Vision to score relevance, skips gaming products, auto-sends best deal
8. **Weekly FAQ** — Claude generates the most frequently asked olim question of the week with a full answer in FR + RU
9. **Manual sends** — send any FR message (with auto-translate to RU) to FR group, RU group, or both; supports scheduling by date and time
10. **Community recommendations** — public form at `/recommander` for members to submit doctors/prestataires they know; stored in DB for admin review

## Architecture

```
nginx (HTTPS, auth_basic) ──► FastAPI backend ──► SQLite
                                    │
                                    ├── RSS scraper (Jerusalem Post)
                                    ├── Telegram scraper (4 channels)
                                    ├── AI processors (Claude Haiku — FR + RU in parallel)
                                    ├── Digest / FAQ generators
                                    ├── Publisher (Whapi.Cloud → FR group + RU group)
                                    └── Scheduler (dispatcher every 15 min via cron)

Local Mac ──► scripts/*_local.py ──► POST /api/scrape/*/manual
```

## Stack

| Layer | Tech |
|---|---|
| Server | Hetzner VPS CX23, Falkenstein |
| Reverse proxy | nginx + Let's Encrypt (Certbot) |
| Backend | FastAPI (Python) |
| Database | SQLite (aiosqlite, one connection per request) |
| AI | Claude Haiku (Anthropic) |
| WhatsApp | Whapi.Cloud |
| Infra | Docker Compose |

## Content categories

| Category | Table | Image (FR) | Image (RU) |
|---|---|---|---|
| News digest | `digests` | alia_actualites_fr.png | ALIA_ACTUALITE_RUSSIAN.png |
| Guide (tip) | `tips` | alia_guide_fr.png | ALIA_GUIDE_RUSSIAN.png |
| Droits | `weekly_rights` | alia_droits_fr.png | alia_droits_russian.png |
| Prestataire | `weekly_prestataire` | alia_prestataires_fr.png | ALIA_PRESTATAIRES_RUSSIAN.png |
| Kids events | `weekly_events_kids` | alia_enfants_fr.png | ALIA_ENFANTS_RUSSIAN.png |
| Médecins | `weekly_doctors` | alia_medecins_fr.png | ALIA_MEDECINS_RUSSIAN.png |
| Deals | `deals` | alia_bon_plans_fr.png | ALIA_BON_PLANS_RUSSIAN.png |
| FAQ | `faqs` | alia_questions_fr.png | ALIA_QUESTIONS_RUSSIAN.png |

Each category sends the FR image to the FR group and the RU image to the RU group.

## WhatsApp groups

| Group | ID |
|---|---|
| FR | `120363426387906348@g.us` |
| RU | `120363430243678300@g.us` |

## Local scrapers (run on Mac)

These scripts run on a Mac because the target sites block server IPs.

| Script | What it does | When to run |
|---|---|---|
| `scripts/kolzchut_local.py` | Scrapes Kol Zchut tip → `/api/scrape/tips/manual` | Weekly |
| `scripts/droits_local.py` | Scrapes Kol Zchut rights → `/api/scrape/rights/manual` | Weekly |
| `scripts/prestataire_local.py` | Sends prestataire data → `/api/scrape/prestataire/manual` | Weekly |
| `scripts/events_kids_local.py` | Scrapes kids events → `/api/scrape/events-kids/manual` | Weekly |

All scripts use ISO week numbers via `isocalendar()` to match the server.

## Telegram deal channels

| Channel | Category |
|---|---|
| shufersaloffocial | Supermarket |
| payngoil | Electronics |
| SecretFlights | Flights |
| hotelscoil | Hotels |

Gaming products (consoles, video games, gaming accessories) are automatically filtered out. Food, supermarket, and general electronics pass.

## Scheduler

The dispatcher (`scripts/dispatcher_server.sh`) runs every 15 minutes via cron on the server and:
- Fires any due scheduled jobs (news, deals, tip, FAQ, prestataire, kids, rights, doctors)
- Fires any pending manual messages from `scheduled_manual` (within ±7 min of their `send_at` time)

All times use Israel time (Asia/Jerusalem). Week numbers are ISO (`isocalendar()`).

## API endpoints

### Scrape / generate
| Method | Path | Description |
|---|---|---|
| POST | `/api/scrape/news` | Fetch Jerusalem Post RSS + AI-process + generate digest |
| POST | `/api/scrape/telegram-deals` | Scrape Telegram deals + process with AI |
| POST | `/api/scrape/tips/manual` | Receive tip from Mac scraper |
| POST | `/api/scrape/rights/manual` | Receive rights content from Mac scraper |
| POST | `/api/scrape/prestataire/manual` | Receive prestataire data from Mac scraper |
| POST | `/api/scrape/events-kids/manual` | Receive kids events from Mac scraper |
| POST | `/api/scrape/cleanup` | Delete old sent/rejected content |

### Publish
| Method | Path | Description |
|---|---|---|
| POST | `/api/publish/article/{id}` | Publish article to WhatsApp |
| POST | `/api/publish/tip/{id}` | Publish guide tip |
| POST | `/api/publish/deal/{id}` | Publish deal (audience-aware) |
| POST | `/api/publish/faq/{id}` | Publish FAQ |
| POST | `/api/publish/digest/{id}` | Publish digest |
| POST | `/api/publish/digest/latest` | Publish most recent digest |
| POST | `/api/publish/prestataire/{id}` | Publish prestataire |
| POST | `/api/publish/kids/{id}` | Publish kids events |
| POST | `/api/publish/rights/{id}` | Publish droits |
| POST | `/api/publish/doctors/{id}` | Publish médecins |
| POST | `/api/publish/manual` | Send manual message (supports scheduling) |
| POST | `/api/publish/translate` | Translate FR → RU via Claude Haiku |
| GET | `/api/publish/scheduled-manual` | List pending scheduled messages |
| DELETE | `/api/publish/scheduled-manual/{id}` | Cancel a scheduled message |
| POST | `/api/publish/fire-scheduled-manual` | Run due scheduled messages (called by dispatcher) |

### Recommendations (public, no auth)
| Method | Path | Description |
|---|---|---|
| POST | `/api/recommendations` | Submit a recommendation (public form) |
| GET | `/api/recommendations` | List recommendations (admin) |
| PATCH | `/api/recommendations/{id}/status` | Approve / reject |
| DELETE | `/api/recommendations/{id}` | Delete |

### Content
| Method | Path | Description |
|---|---|---|
| GET | `/api/articles` | List articles |
| GET | `/api/tips` | List tips |
| GET | `/api/deals` | List deals |
| GET | `/api/faqs` | List FAQs |
| GET | `/api/digests` | List digests |
| GET | `/api/weekly-events/prestataire` | Current week prestataire |
| GET | `/api/weekly-events/kids` | Current week kids events |
| GET | `/api/weekly-events/rights` | Current week rights |
| GET | `/api/weekly-events/doctors` | Current week doctors |

## Dashboard

Accessible at `https://alia-channel.com` (password protected via nginx `auth_basic`).

Features:
- View and validate all content categories
- Edit FR/RU content inline before sending
- One-click publish per item
- Manual send tab: write FR message, auto-translate to RU, choose audience, schedule for later
- Scheduled messages list with cancel option
- "Appel à recommandations" panel: preview and edit the FR/RU recommendation-request message, send to groups

## Public recommendation form

URL: `https://alia-channel.com/recommander`

No authentication required. Members fill in:
- Type (médecin / prestataire)
- Name, specialty, city, phone, language spoken (FR/RU/both)
- Notes, submitted by (optional)

Submissions stored in the `recommendations` table with status `pending`. Admin reviews from dashboard.

## Services

| URL | Service |
|---|---|
| https://alia-channel.com | Dashboard (auth required) |
| https://alia-channel.com/api | FastAPI backend |
| https://alia-channel.com/docs | Swagger UI |
| https://alia-channel.com/recommander | Public recommendation form |

## Environment variables

Copy `.env.template` to `.env` and fill in:

```
ANTHROPIC_API_KEY=
WHAPI_TOKEN=
WHAPI_GROUP_FR=120363426387906348@g.us
WHAPI_GROUP_RU=120363430243678300@g.us
DOMAIN=alia-channel.com
```

## Deploy

```bash
# First time
bash scripts/setup_server.sh
bash scripts/init_https.sh

# Start
docker compose up -d

# Update code
git pull && docker compose restart backend

# Deploy new nginx config
scp scripts/nginx.conf root@167.233.204.172:/opt/alia-channel/scripts/nginx.conf
docker compose restart nginx

# Upload new images
scp alia_*.png ALIA_*.png root@167.233.204.172:/opt/alia-channel/backend/static/
docker compose restart backend
```

## Server path

All files live at `/opt/alia-channel/` on `167.233.204.172`.
SQLite DB is at `/data/alia.db` inside the `alia_backend` container.

## Phases

- [x] Phase 1 — Infrastructure (VPS, Docker, nginx, HTTPS)
- [x] Phase 2 — Scrapers (RSS, Kol Zchut local, Telegram deals)
- [x] Phase 3 — AI Processing (Claude Haiku, FR + RU in parallel, relevance scoring)
- [x] Phase 4 — WhatsApp publishing (Whapi.Cloud, per-audience images)
- [x] Phase 5 — Weekly FAQ generator (deduplication over 8 weeks)
- [x] Phase 6 — Daily news digest
- [x] Phase 7 — Validation dashboard
- [x] Phase 8 — Per-category FR + RU avatar images
- [x] Phase 9 — Manual send with scheduling + auto-translate
- [x] Phase 10 — Public recommendation form + admin review
- [ ] Phase 11 — Instagram publishing (Meta Graph API)
- [ ] Phase 12 — Monitoring + alerts
