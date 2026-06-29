# WhatsApp Number Warm-up Protocol

## Why
WhatsApp bans numbers that suddenly send bulk messages.
A new number must be "warmed up" over 2 weeks before automation starts.

## Requirements
- A dedicated Israeli SIM card (+972) — never your personal number
- The number must be active on a real phone for 2 weeks before connecting to Whapi.Cloud

---

## Week 1 — Manual activity (Days 1–7)

Do this manually every day from the phone:

- Send 5–10 messages to real contacts (friends, family)
- Join 2–3 WhatsApp groups
- Reply to messages you receive
- Change profile photo and status
- Do NOT send any bulk or automated messages yet

Goal: WhatsApp sees this as a normal human number.

---

## Week 2 — Gradual volume (Days 8–14)

- Connect the number to Whapi.Cloud (scan QR code)
- Send 1–2 test messages per day via the API
- Increase to 5 messages/day by Day 12
- Increase to 10 messages/day by Day 14
- Always use randomized delays between sends (30–120 seconds)

---

## Day 15+ — Normal operation

- Pipeline is active
- Randomized delays between each message send
- Never send more than 50 messages/hour
- Keep a backup number ready (same warm-up process in parallel)

---

## Red flags that trigger a ban
- Sending to numbers that haven't saved you as a contact
- Sending identical messages repeatedly
- High volume suddenly with no warm-up
- Too many "report spam" from recipients
