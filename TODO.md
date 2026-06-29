# AL.IA Channel — TODO

## Phase 1 — Infrastructure
- [x] docker-compose.yml
- [x] setup_server.sh
- [x] init_https.sh
- [x] nginx.conf (reverse proxy)
- [x] .env.template
- [x] warmup_whatsapp.md
- [ ] Create Hetzner account + server
- [ ] Point domain DNS to server IP
- [ ] Run setup_server.sh on VPS
- [ ] Run init_https.sh (SSL certificate)
- [ ] docker compose up -d (all services running)

## Phase 2 — Scrapers
- [x] SQLite schema (articles, tips, logs)
- [x] RSS sources list with FR/RU routing
- [x] RSS scraper (parallel fetch + deduplication)
- [x] Kol Zchut weekly scraper
- [ ] Create Anthropic account + API key
- [ ] Create Whapi.Cloud account
- [ ] Buy prepaid SIM + start WhatsApp warm-up ⚠️ do today

## Phase 3 — AI Processing
- [ ] Claude Haiku processor (FR + RU in parallel)
- [ ] Relevance scoring
- [ ] Category detection
- [ ] WhatsApp CTA generation
- [ ] Instagram caption generation
- [ ] Kol Zchut tip reformatter (FR + RU)

## Phase 4 — Image Generation
- [ ] Pillow template (logo + title + category)
- [ ] FR and RU versions
- [ ] Preview in dashboard

## Phase 5 — Dashboard
- [ ] FastAPI backend + endpoints
- [ ] HTML/JS validation dashboard
- [ ] FR / RU language toggle
- [ ] Tabs: News / Kol Zchut Tips
- [ ] Approve / Reject / Edit actions
- [ ] Channel selector (WhatsApp FR / RU / Instagram)
- [ ] Schedule send time per article

## Phase 6 — WhatsApp Publishing
- [ ] Whapi.Cloud integration
- [ ] Send to FR sub-group
- [ ] Send to RU sub-group
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
- [ ] Scrape every 3 hours workflow
- [ ] AI processing trigger workflow
- [ ] Sunday Kol Zchut workflow
- [ ] Approved article → publish workflow

## Phase 9 — Monitoring
- [ ] Structured logs (scrape / AI / publish)
- [ ] Error alerts (email or Telegram)
- [ ] WhatsApp metrics (subscribers, retention)
- [ ] Instagram metrics (reach, engagement)
