# AL.IA Channel — TODO

## Phase 1 — Infrastructure
- [x] docker-compose.yml
- [x] setup_server.sh
- [x] init_https.sh
- [x] nginx.conf (reverse proxy)
- [x] .env.template
- [x] warmup_whatsapp.md
- [x] Create Hetzner account + server (167.233.204.172, CX23, Falkenstein)
- [x] Point domain DNS to server IP (alia-channel.com → A record)
- [x] Run setup_server.sh on VPS
- [x] Run init_https.sh (SSL certificate)
- [x] docker compose up -d (all services running)

## Phase 2 — Scrapers
- [x] SQLite schema (articles, tips, logs, deals)
- [x] RSS sources list with FR/RU routing
- [x] RSS scraper (parallel fetch + deduplication)
- [x] Kol Zchut weekly scraper
- [x] Create Anthropic account + API key
- [x] Create Whapi.Cloud account
- [x] Buy prepaid SIM + connect to Whapi.Cloud
- [x] Telegram deal scraper (4 channels: supermarket, electronics, flights, hotels)
- [ ] WhatsApp warm-up protocol (gradually increase message volume)

## Phase 3 — AI Processing
- [x] Claude Haiku processor for articles (FR + RU in parallel)
- [x] Relevance scoring for articles
- [x] Category detection
- [x] WhatsApp CTA generation
- [x] Instagram caption generation
- [x] Kol Zchut tip reformatter (FR + RU)
- [x] Deal processor — relevance scoring with expiry check + audience detection (fr/ru/both)
- [x] Deal content generation (FR + RU, audience-aware)
- [x] Relevance hierarchy (flights FR/RU > electronics > food > hotels)

## Phase 4 — Image Generation
- [ ] Pillow template (logo + title + category)
- [ ] FR and RU versions
- [ ] Preview in dashboard

## Phase 5 — Dashboard
- [ ] HTML/JS validation dashboard
- [ ] FR / RU language toggle
- [ ] Tabs: News / Kol Zchut Tips / Deals
- [ ] Approve / Reject / Edit actions
- [ ] Channel selector (WhatsApp FR / RU / Instagram)
- [ ] Schedule send time per article

## Phase 6 — WhatsApp Publishing
- [x] Whapi.Cloud integration
- [x] Send articles to FR group
- [x] Send articles to RU group
- [x] Send deals to FR group (audience-aware)
- [x] Send deals to RU group (audience-aware)
- [ ] Randomized delays anti-ban
- [ ] Backup number support
- [ ] Error alerts on send failure

## Phase 7 — Instagram Publishing
- [ ] Meta Graph API integration
- [ ] FR + RU posts on @alia.channel
- [ ] Image + caption auto-publish
- [ ] Randomized delays anti-ban
- [ ] Carousel format support

## Phase 8 — n8n Workflows
- [ ] Scrape news every 3 hours workflow
- [ ] Scrape deals weekly workflow (per category)
- [ ] AI processing trigger workflow
- [ ] Sunday Kol Zchut workflow (automate kolzchut_local.py on Mac via cron)
- [ ] Approved article → publish workflow

## Phase 9 — Monitoring
- [ ] Structured logs (scrape / AI / publish)
- [ ] Error alerts (email or Telegram)
- [ ] WhatsApp metrics (subscribers, retention)
- [ ] Instagram metrics (reach, engagement)
