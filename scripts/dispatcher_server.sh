#!/bin/bash
# Alia server-side dispatcher — runs every 15 minutes via cron

BASE="http://localhost:8000"
LOG="/var/log/alia-cron.log"

echo "[$(date -u '+%Y-%m-%d %H:%M')] Dispatcher running..." >> "$LOG"

DUE=$(curl -s "${BASE}/api/schedules/due?location=server")
JOBS=$(echo "$DUE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for j in data.get('due', []):
    print(j['job_key'])
" 2>/dev/null)

if [ -z "$JOBS" ]; then
    echo "[$(date -u '+%Y-%m-%d %H:%M')] Nothing due." >> "$LOG"
    exit 0
fi

run_job() {
    local JOB="$1"
    echo "[$(date -u '+%Y-%m-%d %H:%M')] Running: $JOB" >> "$LOG"
    case "$JOB" in
        news_digest)
            RESULT=$(curl -s -X POST "${BASE}/api/scrape/news") ;;
        telegram_deals)
            RESULT=$(curl -s -X POST "${BASE}/api/scrape/telegram-deals") ;;
        faq)
            RESULT=$(curl -s -X POST "${BASE}/api/faqs/generate") ;;
        kol_zchut)
            RESULT=$(curl -s -X POST "${BASE}/api/scrape/tips") ;;
        scrape_kol_zchut)
            RESULT=$(curl -s -X POST "${BASE}/api/scrape/tips") ;;
        generate_kids_events)
            RESULT=$(curl -s -X POST "${BASE}/api/scrape/events-kids/generate") ;;
        generate_prestataire)
            RESULT=$(curl -s -X POST "${BASE}/api/scrape/prestataire/generate") ;;
        generate_kol_zchut)
            RESULT=$(curl -s -X POST "${BASE}/api/scrape/tips/generate") ;;
        *)
            RESULT="unknown job: $JOB" ;;
    esac
    echo "[$(date -u '+%Y-%m-%d %H:%M')] Done: $JOB → $RESULT" >> "$LOG"
    curl -s -X POST "${BASE}/api/schedules/${JOB}/run" > /dev/null 2>&1
}

while IFS= read -r JOB; do
    [ -n "$JOB" ] && run_job "$JOB"
done <<< "$JOBS"
