import json
import logging
import os
from datetime import datetime

import anthropic

from db.database import get_db

logger = logging.getLogger(__name__)
claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

FR_PROMPT = """Tu es rédacteur pour Alia Channel, une communauté WhatsApp pour les olim francophones en Israël.
Voici les infos d'un prestataire de service recommandé sur Midrag (site d'avis israélien) :

Nom : {name}
Service : {category}
Ville : {city}
Note : {rating}/10
Nombre d'avis : {reviews}
Satisfaction : {satisfaction}% très satisfaits

Écris un message WhatsApp en suivant EXACTEMENT ce format :

🛠️ Le Réseau Alia

[Commence par une phrase avec une emoji thématique sur le contexte saisonnier ou la situation olim qui explique pourquoi beaucoup cherchent un(e) {category} cette semaine]

Grâce à notre partenariat avec Midrag, Alia peut désormais vous orienter vers un professionnel recommandé.

[Présente le prestataire : nom, note, ville, fiabilité en 1-2 lignes max]

🤖 Décrivez simplement votre problème à Alia.

📢 Rejoignez la communauté Alia pour découvrir d'autres services utiles aux olim.

IMPORTANT : traduis en français le nom du service ({category}) et le titre professionnel hébreu dans le nom du prestataire (ex: רו"ח = expert-comptable, שרברב = plombier, חשמלאי = électricien, etc.). Écris le nom du prestataire en translittération latine si nécessaire.
N'invente rien, base-toi uniquement sur les infos fournies. Pas de markdown, pas de titre."""

RU_PROMPT = """Ты редактор Alia Channel — WhatsApp-сообщества для русскоязычных олим в Израиле.
Вот данные рекомендованного специалиста с сайта Мидраг (израильский сайт отзывов):

Имя : {name}
Услуга : {category}
Город : {city}
Оценка : {rating}/10
Количество отзывов : {reviews}
Удовлетворённость : {satisfaction}% очень довольны

Напиши WhatsApp-сообщение, строго следуя этому формату :

🛠️ Сеть Alia

[Начни с предложения с тематическим эмодзи о сезонном контексте или ситуации олим, объясняющего почему многие ищут {category} на этой неделе]

Благодаря нашему партнёрству с Midrag, Alia теперь может направить вас к рекомендованному специалисту.

[Представь специалиста: имя, оценка, город, надёжность — максимум 1-2 строки]

🤖 Просто опишите свою проблему Alia.

📢 Присоединяйтесь к сообществу Alia, чтобы узнавать о других полезных услугах для олим.

ВАЖНО : переведи на русский язык название услуги ({category}) и профессиональный иврит-префикс в имени специалиста (например: רו"ח = бухгалтер/CPA, שרברב = сантехник, חשמלאי = электрик и т.д.). Имя специалиста напиши в русской транслитерации если нужно.
Не придумывай ничего, опирайся только на предоставленные данные. Без markdown, без заголовков."""


async def generate_weekly_prestataire(force: bool = False, data: dict | None = None) -> dict:
    import asyncio
    week = datetime.utcnow().strftime("%Y-W%W")

    async with get_db() as db:
        cursor = await db.execute("SELECT id, content_fr, raw_payload FROM weekly_prestataire WHERE week = ?", (week,))
        existing = await cursor.fetchone()

    if existing and existing["content_fr"] and not force:
        return {"status": "skipped", "week": week, "prestataire_id": existing["id"]}

    if not data:
        if existing and existing["raw_payload"]:
            data = json.loads(existing["raw_payload"])
        else:
            return {"status": "error", "reason": "no data stored for this week"}

    satisfaction_str = f"{data['satisfaction']}%" if data.get("satisfaction") else "N/A"

    fr_resp, ru_resp = await asyncio.gather(
        claude.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=200,
            messages=[{"role": "user", "content": FR_PROMPT.format(
                name=data["name"], category=data["category"], city=data["city"],
                rating=data["rating"], reviews=data["reviews"], satisfaction=satisfaction_str
            )}]
        ),
        claude.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=200,
            messages=[{"role": "user", "content": RU_PROMPT.format(
                name=data["name"], category=data["category"], city=data["city"],
                rating=data["rating"], reviews=data["reviews"], satisfaction=satisfaction_str
            )}]
        ),
    )

    content_fr = fr_resp.content[0].text.strip()
    content_ru = ru_resp.content[0].text.strip()

    # Append source URL + Midrag CTA + Alia CTA
    content_fr += (
        f"\n\n🔗 {data['url']}"
        "\n\n👉 Vous cherchez un autre professionnel ? Parlez directement à Lotem, notre assistante Midrag :\nhttps://wa.me/972556891818?text=Salut,%20Lotem%20!%20Aide-moi%20à%20trouver%20un%20professionnel"
        "\n\n🤖 Ou posez vos questions à Alia :\nhttps://wa.me/972549675013?text=Aide-moi"
    )
    content_ru += (
        f"\n\n🔗 {data['url']}"
        "\n\n👉 Ищете другого специалиста? Напишите Лотем, нашему ассистенту Midrag :\nhttps://wa.me/972556891818?text=Привет,%20Лотем!%20Помоги%20мне%20найти%20специалиста"
        "\n\n🤖 Или задайте вопрос Alia :\nhttps://wa.me/972549675013?text=Помоги"
    )

    async with get_db() as db:
        if existing:
            await db.execute(
                "UPDATE weekly_prestataire SET data_json = ?, content_fr = ?, content_ru = ? WHERE week = ?",
                (json.dumps(data, ensure_ascii=False), content_fr, content_ru, week),
            )
            await db.commit()
            record_id = existing["id"]
        else:
            cursor = await db.execute(
                "INSERT INTO weekly_prestataire (week, data_json, content_fr, content_ru, created_at) VALUES (?, ?, ?, ?, ?)",
                (week, json.dumps(data, ensure_ascii=False), content_fr, content_ru, datetime.utcnow().isoformat()),
            )
            await db.commit()
            record_id = cursor.lastrowid

    logger.info(f"[prestataire] Generated #{record_id} for {week}: {data['name']} ({data['category']})")
    return {"status": "generated", "week": week, "prestataire_id": record_id}
