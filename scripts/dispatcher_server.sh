#!/bin/bash
# Alia server-side dispatcher — runs every 15 minutes via cron

BASE="http://localhost:8000"
LOG="/var/log/alia-cron.log"

ADMIN_API_KEY=$(grep -m1 '^ADMIN_API_KEY=' /opt/alia-channel/.env | cut -d= -f2-)
AUTH=(-H "X-Admin-Key: ${ADMIN_API_KEY}")

echo "[$(date -u '+%Y-%m-%d %H:%M')] Dispatcher running..." >> "$LOG"

# Always check for due scheduled manual messages
curl -s "${AUTH[@]}" -X POST "${BASE}/api/publish/fire-scheduled-manual" > /dev/null 2>&1

DUE=$(curl -s "${AUTH[@]}" "${BASE}/api/schedules/due?location=server")
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
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/scrape/news") ;;
        scrape_news)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/scrape/news") ;;
        send_news)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/publish/send-pending/digest") ;;
        telegram_deals)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/scrape/telegram-deals") ;;
        scrape_deals)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/scrape/telegram-deals") ;;
        send_deals)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/publish/send-pending/deal") ;;
        faq|generate_faq)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/faqs/generate") ;;
        kol_zchut)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/scrape/tips") ;;
        scrape_kol_zchut)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/scrape/tips") ;;
        generate_kids_events)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/scrape/events-kids/generate") ;;
        generate_prestataire)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/scrape/prestataire/generate") ;;
        generate_kol_zchut)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/scrape/tips/generate") ;;
        generate_doctor)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/doctors/generate") ;;
        generate_rights)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/scrape/rights/generate") ;;
        send_digest)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/publish/send-pending/digest") ;;
        send_tip)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/publish/send-pending/tip") ;;
        send_faq)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/publish/send-pending/faq") ;;
        send_rights)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/publish/send-pending/rights") ;;
        send_doctor)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/publish/send-pending/doctor") ;;
        send_kids)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/publish/send-pending/kids") ;;
        send_prestataire)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/publish/send-pending/prestataire") ;;
        send_deal)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/publish/send-pending/deal") ;;
        queue_send_guide)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/queue/send/guide") ;;
        queue_send_droits)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/queue/send/droits") ;;
        queue_send_prestataire)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/queue/send/prestataire") ;;
        queue_send_kids)
            RESULT=$(curl -s "${AUTH[@]}" -X POST "${BASE}/api/queue/send/kids") ;;
        *)
            RESULT="unknown job: $JOB" ;;
    esac
    echo "[$(date -u '+%Y-%m-%d %H:%M')] Done: $JOB → $RESULT" >> "$LOG"
    curl -s "${AUTH[@]}" -X POST "${BASE}/api/schedules/${JOB}/run" > /dev/null 2>&1
}

while IFS= read -r JOB; do
    [ -n "$JOB" ] && run_job "$JOB"
done <<< "$JOBS"
