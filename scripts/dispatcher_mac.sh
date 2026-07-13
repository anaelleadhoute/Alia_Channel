#!/bin/bash
# Alia Mac dispatcher — runs hourly via crontab
# Checks which mac jobs are due and runs local Playwright scrapers

BASE="https://alia-channel.com"
DIR="/Users/anaelleadhoute/Desktop/Alia_Community"
LOG="/tmp/alia-mac-cron.log"

echo "[$(date -u '+%Y-%m-%d %H:%M')] Mac dispatcher running..." >> $LOG

DUE=$(curl -s "${BASE}/api/schedules/due?location=mac")
JOBS=$(echo "$DUE" | python3 -c "import sys,json; [print(j['job_key']) for j in json.load(sys.stdin).get('due',[])]" 2>/dev/null)

for JOB in $JOBS; do
    echo "[$(date -u '+%Y-%m-%d %H:%M')] Running: $JOB" >> $LOG
    case "$JOB" in
        kids_events)
            python3 "${DIR}/scripts/events_kids_local.py" >> $LOG 2>&1 ;;
        prestataire)
            python3 "${DIR}/scripts/prestataire_local.py" >> $LOG 2>&1 ;;
    esac
    curl -s -X POST "${BASE}/api/schedules/${JOB}/run" >> /dev/null
    echo "" >> $LOG
done
