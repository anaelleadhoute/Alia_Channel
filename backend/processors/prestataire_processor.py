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

Écris un court message WhatsApp (3-4 phrases max) dans ce style :
- Commence par "⭐ Prestataire de la semaine !"
- Deuxième phrase : explique que beaucoup d'olim cette semaine ont demandé un(e) {category}, alors Alia en a trouvé un(e) pour eux
- Présente ensuite le prestataire avec son nom, sa note et sa fiabilité
- Ton chaleureux et communautaire, comme si un ami donnait un bon plan

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

Напиши короткое WhatsApp-сообщение (3-4 предложения) в таком стиле :
- Начни с "⭐ Специалист недели!"
- Второе предложение : на этой неделе многие олим спрашивали про {category} — и Alia нашла для них специалиста
- Затем представь специалиста с именем, оценкой и надёжностью
- Тёплый, дружеский тон — как совет от друга

ВАЖНО : переведи на русский язык название услуги ({category}) и профессиональный иврит-префикс в имени специалиста (например: רו"ח = бухгалтер/CPA, שרברב = сантехник, חשמלאי = электрик и т.д.). Имя специалиста напиши в русской транслитерации если нужно.
Не придумывай ничего, опирайся только на предоставленные данные. Без markdown, без заголовков."""


async def generate_weekly_prestataire(force: bool = False, data: dict | None = None) -> dict:
    import asyncio
    week = datetime.utcnow().strftime("%Y-W%W")

    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM weekly_prestataire WHERE week = ?", (week,))
        existing = await cursor.fetchone()
    if existing and not force:
        return {"status": "skipped", "week": week, "prestataire_id": existing["id"]}

    if not data:
        return {"status": "error", "reason": "no data provided"}

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

    # Append source URL
    content_fr += f"\n\n🔗 {data['url']}"
    content_ru += f"\n\n🔗 {data['url']}"

    async with get_db() as db:
        if force:
            await db.execute("DELETE FROM weekly_prestataire WHERE week = ?", (week,))
        cursor = await db.execute(
            "INSERT INTO weekly_prestataire (week, data_json, content_fr, content_ru, created_at) VALUES (?, ?, ?, ?, ?)",
            (week, json.dumps(data, ensure_ascii=False), content_fr, content_ru, datetime.utcnow().isoformat()),
        )
        await db.commit()
        record_id = cursor.lastrowid

    logger.info(f"[prestataire] Generated #{record_id} for {week}: {data['name']} ({data['category']})")
    return {"status": "generated", "week": week, "prestataire_id": record_id}
