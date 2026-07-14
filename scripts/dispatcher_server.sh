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

    local ENDPOINT=""
    case "$JOB" in
        news_digest)          ENDPOINT="${BASE}/api/scrape/news" ;;
        telegram_deals)       ENDPOINT="${BASE}/api/scrape/telegram-deals" ;;
        faq)                  ENDPOINT="${BASE}/api/faqs/generate" ;;
        kol_zchut)             ENDPOINT="${BASE}/api/scrape/tips" ;;
        scrape_kol_zchut)      ENDPOINT="${BASE}/api/scrape/tips" ;;
        generate_kids_events)  ENDPOINT="${BASE}/api/scrape/events-kids/generate" ;;
        generate_prestataire)  ENDPOINT="${BASE}/api/scrape/prestataire/generate" ;;
        generate_kol_zchut)    ENDPOINT="${BASE}/api/scrape/tips/generate" ;;
        *)
            echo "[$(date -u '+%Y-%m-%d %H:%M')] FAILED: $JOB → unknown job, NOT marking as ran" >> "$LOG"
            return ;;
    esac

    # Capture HTTP status separately from the body so a failed/erroring job
    # is never marked as "ran" — that used to silently suppress retries for
    # up to 23h (daily) or 6 days (weekly) with no alert.
    local RESPONSE HTTP_CODE BODY
    RESPONSE=$(curl -s -w '\n%{http_code}' -X POST "$ENDPOINT")
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')

    if [[ "$HTTP_CODE" =~ ^2 ]]; then
        echo "[$(date -u '+%Y-%m-%d %H:%M')] Done: $JOB → $BODY" >> "$LOG"
        curl -s -X POST "${BASE}/api/schedules/${JOB}/run" > /dev/null 2>&1
    else
        echo "[$(date -u '+%Y-%m-%d %H:%M')] FAILED: $JOB (HTTP $HTTP_CODE) → $BODY — NOT marking as ran, will retry next window" >> "$LOG"
    fi
}

while IFS= read -r JOB; do
    [ -n "$JOB" ] && run_job "$JOB"
done <<< "$JOBS"
