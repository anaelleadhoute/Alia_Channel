"""
Content queue — pre-generated content sent one per week.
Categories: guide, droits, prestataire, kids, pharma, supermarket
"""
import asyncio
import json
import logging
import os
import random
from datetime import datetime
from typing import Optional

import anthropic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)
claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

WHAPI_TOKEN = os.getenv("WHAPI_TOKEN", "")
WHAPI_GROUP_FR = os.getenv("WHAPI_GROUP_FR", "")
WHAPI_GROUP_RU = os.getenv("WHAPI_GROUP_RU", "")

# ── Prompts ──────────────────────────────────────────────────────────────────

PROMPTS = {
    "guide": {
        "fr": """Tu es rédacteur pour AL.IA Channel, un média pour les olim francophones en Israël.

Voici du contenu issu d'une source officielle israélienne :
Source : {url}
Contenu : {content}

Rédige un "Guide Alia" en français pour les nouveaux olim. Choisis UNE question concrète et fréquente liée à ce contenu.

Format EXACT à respecter :
📄 Le Guide Alia

Beaucoup d'utilisateurs d'Alia nous demandent :

"[La question fréquente entre guillemets]"

✅ [Réponse claire et concrète en 2-3 phrases]

⚠️ [Une mise en garde ou nuance importante, si pertinente]

🤖 Pour connaître la procédure adaptée à votre situation, demandez à Alia.
https://wa.me/972549675013?text=Aide-moi

Réponds uniquement avec le texte du guide, sans JSON, sans commentaire.""",
        "ru": """Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Вот контент из официального израильского источника :
Источник : {url}
Содержание : {content}

Напиши "Гид Alia" на русском для новых олим. Выбери ОДИН конкретный и частый вопрос по этой теме.

ТОЧНЫЙ формат :
📄 Гид Alia

Многие пользователи Alia спрашивают :

"[Частый вопрос в кавычках]"

✅ [Чёткий и конкретный ответ в 2-3 предложениях]

⚠️ [Важная оговорка или нюанс, если есть]

🤖 Чтобы узнать процедуру для вашей ситуации, спросите у Alia.
https://wa.me/972549675013?text=Помоги

Отвечай только текстом гида, без JSON, без комментариев.""",
    },
    "droits": {
        "fr": """Tu es rédacteur pour AL.IA Channel, média pour les olim francophones en Israël.

Voici une page de Kol Zchut sur les droits et aides en Israël :
Source : {url}
Contenu : {content}

Rédige un message "Les Droits Alia" en français (80-100 mots) sur un droit ou une aide disponible pour les olim.

Format EXACT :
💰 Les Droits Alia

💡 Le saviez-vous ?

[1 fait concret et utile sur ce droit/cette aide : qui peut en bénéficier, montant, conditions principales]

✅ [Ce que vous pouvez faire concrètement pour en bénéficier]

🤖 Pour plus d'informations, demandez à Alia.
https://wa.me/972549675013?text=Aide-moi

Réponds uniquement avec le texte, sans JSON.""",
        "ru": """Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Вот страница Kol Zchut о правах и льготах в Израиле :
Источник : {url}
Содержание : {content}

Напиши сообщение "Права Alia" на русском (80-100 слов) о праве или льготе, доступной для олим.

ТОЧНЫЙ формат :
💰 Права Alia

💡 Знаете ли вы ?

[1 конкретный и полезный факт об этом праве/льготе: кто может получить, сумма, основные условия]

✅ [Что можно сделать конкретно, чтобы воспользоваться этим правом]

🤖 Для получения дополнительной информации спросите у Alia.
https://wa.me/972549675013?text=Помоги

Отвечай только текстом, без JSON.""",
    },
    "prestataire": {
        "fr": """Tu es rédacteur pour Alia Channel, une communauté WhatsApp pour les olim francophones en Israël.
Voici les infos d'un prestataire de service recommandé sur Midrag (site d'avis israélien) :

Nom : {name}
Service : {category}
Ville : {city}
Note : {rating}/10
Nombre d'avis : {reviews}
Satisfaction : {satisfaction}% très satisfaits

Écris un message WhatsApp en suivant EXACTEMENT ce format :

🛠️ Le Réseau Alia

[Commence par une phrase avec une emoji thématique qui présente ce professionnel de façon engageante]

Grâce à notre partenariat avec Midrag, Alia peut désormais vous orienter vers un professionnel recommandé.

[Présente le prestataire : nom, note, ville, fiabilité en 1-2 lignes max]

🔗 Voir son profil Midrag : {url}

👉 Vous cherchez un autre professionnel ? Parlez directement à Lotem, notre assistante Midrag :
https://wa.me/972556891818?text=Salut,%20Lotem%20!%20Aide-moi%20à%20trouver%20un%20professionnel

📢 Rejoignez la communauté Alia:
https://tinyurl.com/Alia-community

IMPORTANT : traduis en français le nom du service ({category}) et le titre professionnel hébreu. Écris le nom du prestataire en translittération latine si nécessaire.
Mentionne la ville (Tel-Aviv, Netanya ou Jérusalem). N'invente rien. Pas de markdown, pas de titre.""",
        "ru": """Ты редактор Alia Channel — WhatsApp-сообщества для русскоязычных олим в Израиле.
Вот данные рекомендованного специалиста с сайта Мидраг :

Имя : {name}
Услуга : {category}
Город : {city}
Оценка : {rating}/10
Количество отзывов : {reviews}
Удовлетворённость : {satisfaction}% очень довольны

Напиши WhatsApp-сообщение, строго следуя этому формату :

🛠️ Сеть Alia

[Начни с предложения с тематическим эмодзи, которое представляет этого специалиста в привлекательной манере]

Благодаря нашему партнёрству с Midrag, Alia теперь может направить вас к рекомендованному специалисту.

[Представь специалиста: имя, оценка, город, надёжность — максимум 1-2 строки]

🔗 Профиль на Midrag : {url}

👉 Ищете другого специалиста? Напишите Лотем, нашему ассистенту Midrag :
https://wa.me/972556891818?text=Привет,%20Лотем!%20Помоги%20мне%20найти%20специалиста

Присоединяйтесь к сообществу Alia и получайте всё это каждую неделю :
https://tinyurl.com/Alia-community-RU

ВАЖНО : переведи название услуги на русский и имя в транслитерации если нужно.
Без markdown, без заголовков.""",
    },
    "kids": {
        "fr": """Tu es rédacteur pour AL.IA Channel, média pour les olim francophones en Israël.

Une attraction familiale recommandée cette semaine (depuis Karamel.co.il) :
- Nom (en hébreu) : {name}
- Description : {description}

Rédige un message WhatsApp court (80-100 mots) au format EXACT :
👨‍👩‍👧 Sortie famille — Alia

Sur ces 7 derniers jours, {families_count} familles d'Alia ont demandé une idée de sortie avec les enfants.

🎡 Cette semaine, on vous recommande [nom traduit en français], [description courte en français, 1 phrase].

🔗 Plus d'infos : {url}

📢 Rejoignez la communauté Alia:
https://tinyurl.com/Alia-community

Réponds uniquement avec le texte, sans JSON.""",
        "ru": """Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Рекомендуемое семейное место на этой неделе (от Karamel.co.il) :
- Название (на иврите) : {name}
- Описание : {description}

Напиши короткое WhatsApp сообщение (80-100 слов) в точном формате :
👨‍👩‍👧 Семейный досуг — от Alia

За последние 7 дней {families_count} семей из Alia спрашивали об идее для прогулки с детьми.

🎡 На этой неделе рекомендуем [название на русском], [краткое описание на русском, 1 предложение].

🔗 Подробнее : {url}

Присоединяйтесь к сообществу Alia и получайте всё это каждую неделю :
https://tinyurl.com/Alia-community-RU

Отвечай только текстом, без JSON.""",
    },
    "pharma": {
        "fr": """Tu es rédacteur pour AL.IA Channel, un média pour les olim francophones en Israël.

Voici la liste des promotions actuelles chez Super-Pharm (grande chaîne de pharmacies/drugstores en Israël) :

{promotions_text}

Choisis LA SEULE promotion la plus utile et pertinente pour des olim (produits du quotidien : hygiène, soins, produits pour bébé, produits ménagers de base — évite les produits trop spécifiques, les compléments alimentaires obscurs, le papier toilette, ou les articles hors sujet). Rédige un message WhatsApp court (80-100 mots) au format EXACT :

💊 Bon plan Super-Pharm — Alia

Cette semaine, on a repéré une bonne affaire chez Super-Pharm !

🛒 [Nom du produit traduit/expliqué clairement en français] à seulement [prix] ₪.

⏰ Offre valable jusqu'au [date de validité, si disponible].

🔗 Voir toutes les offres : {url}

📢 Rejoignez la communauté Alia:
https://tinyurl.com/Alia-community

Réponds uniquement avec le texte, sans JSON.""",
        "ru": """Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Вот список текущих акций в сети Super-Pharm (крупная сеть аптек/дрогери в Израиле) :

{promotions_text}

Выбери ТОЛЬКО ОДНУ акцию — самую полезную и релевантную для олим (товары повседневного спроса: гигиена, уход, товары для малышей, базовая бытовая химия — избегай слишком специфичных товаров, непонятных БАДов, туалетной бумаги или нерелевантных позиций). Напиши короткое WhatsApp сообщение (80-100 слов) в точном формате :

💊 Выгодное предложение Super-Pharm — Alia

На этой неделе мы заметили отличное предложение в Super-Pharm!

🛒 [Название товара понятно переведено на русский] всего за [цена] ₪.

⏰ Акция действует до [дата окончания, если известна].

🔗 Все акции : {url}

Присоединяйтесь к сообществу Alia и получайте всё это каждую неделю :
https://tinyurl.com/Alia-community-RU

Отвечай только текстом, без JSON.""",
    },
    "supermarket": {
        "fr": """Tu es rédacteur pour AL.IA Channel, un média pour les olim francophones en Israël.

Voici la liste des promotions actuelles chez Shufersal (grande chaîne de supermarchés en Israël) :

{promotions_text}

Choisis LA SEULE promotion la plus utile et pertinente pour des olim (produits alimentaires du quotidien, produits ménagers de base, hygiène — évite les produits trop spécifiques, l'alcool, le papier toilette, ou les articles hors sujet). Rédige un message WhatsApp court (80-100 mots) au format EXACT :

🛒 Bon plan Shufersal — Alia

Cette semaine, on a repéré une bonne affaire chez Shufersal !

🛍️ [Nom du produit traduit/expliqué clairement en français] à seulement [prix] ₪.

⏰ Offre valable jusqu'au [date de validité, si disponible].

🔗 Voir toutes les offres : {url}

📢 Rejoignez la communauté Alia:
https://tinyurl.com/Alia-community

Réponds uniquement avec le texte, sans JSON.""",
        "ru": """Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Вот список текущих акций в сети Shufersal (крупная сеть супермаркетов в Израиле) :

{promotions_text}

Выбери ТОЛЬКО ОДНУ акцию — самую полезную и релевантную для олим (повседневные продукты питания, базовая бытовая химия, гигиена — избегай слишком специфичных товаров, алкоголя, туалетной бумаги или нерелевантных позиций). Напиши короткое WhatsApp сообщение (80-100 слов) в точном формате :

🛒 Выгодное предложение Shufersal — Alia

На этой неделе мы заметили отличное предложение в Shufersal!

🛍️ [Название товара понятно переведено на русский] всего за [цена] ₪.

⏰ Акция действует до [дата окончания, если известна].

🔗 Все акции : {url}

Присоединяйтесь к сообществу Alia и получайте всё это каждую неделю :
https://tinyurl.com/Alia-community-RU

Отвечай только текстом, без JSON.""",
    },
}


def _format_prompt(template: str, payload: dict) -> str:
    try:
        return template.format(**payload)
    except KeyError:
        return template.format_map({k: payload.get(k, "") for k in ["url", "content", "name", "category", "city", "rating", "reviews", "satisfaction", "description", "families_count", "promotions_text"]})


async def _generate_content(category: str, payload: dict) -> tuple[str, str]:
    prompts = PROMPTS.get(category)
    if not prompts:
        raise ValueError(f"Unknown category: {category}")

    if category == "kids":
        payload = {**payload, "families_count": random.randint(1, 7)}

    fr_prompt = _format_prompt(prompts["fr"], payload)
    ru_prompt = _format_prompt(prompts["ru"], payload)

    fr_resp, ru_resp = await asyncio.gather(
        claude.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=512,
            messages=[{"role": "user", "content": fr_prompt}],
        ),
        claude.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=512,
            messages=[{"role": "user", "content": ru_prompt}],
        ),
    )
    return fr_resp.content[0].text.strip(), ru_resp.content[0].text.strip()


CATEGORY_IMAGES_FR = {
    "guide":       "https://alia-channel.com/alia_guide_fr.png",
    "droits":      "https://alia-channel.com/alia_droits_fr.png",
    "prestataire": "https://alia-channel.com/alia_prestataires_fr.png",
    "kids":        "https://alia-channel.com/alia_enfants_fr.png",
    "pharma":      "https://alia-channel.com/alia_bon_plans_fr.png",
    "supermarket": "https://alia-channel.com/alia_bon_plans_fr.png",
}
CATEGORY_IMAGES_RU = {
    "guide":       "https://alia-channel.com/ALIA_GUIDE_RUSSIAN.png",
    "droits":      "https://alia-channel.com/alia_droits_russian.png",
    "prestataire": "https://alia-channel.com/ALIA_PRESTATAIRES_RUSSIAN.png",
    "kids":        "https://alia-channel.com/ALIA_ENFANTS_RUSSIAN.png",
    "pharma":      "https://alia-channel.com/ALIA_BON_PLANS_RUSSIAN.png",
    "supermarket": "https://alia-channel.com/ALIA_BON_PLANS_RUSSIAN.png",
}


async def _whapi_send(group_id: str, text: str, image_url: str | None = None):
    import httpx
    async with httpx.AsyncClient() as client:
        if image_url:
            resp = await client.post(
                "https://gate.whapi.cloud/messages/image",
                params={"token": WHAPI_TOKEN},
                json={"to": group_id, "media": image_url, "caption": text},
                timeout=30,
            )
        else:
            resp = await client.post(
                "https://gate.whapi.cloud/messages/text",
                headers={"Authorization": f"Bearer {WHAPI_TOKEN}", "Content-Type": "application/json"},
                json={"to": group_id, "body": text},
                timeout=30,
            )
        resp.raise_for_status()
        return resp.json()


# ── Models ────────────────────────────────────────────────────────────────────

class QueueAddRequest(BaseModel):
    category: str          # guide | droits | prestataire | kids | pharma | supermarket
    source_url: Optional[str] = None
    raw_payload: dict      # data needed to generate content (url/content or name/category/etc.)
    generate_now: bool = True  # generate FR+RU immediately


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/add")
async def add_to_queue(req: QueueAddRequest):
    """Add one item to the content queue. Optionally generates FR+RU immediately."""
    if req.category not in PROMPTS:
        raise HTTPException(status_code=400, detail=f"Unknown category '{req.category}'")

    content_fr = content_ru = None
    if req.generate_now:
        try:
            content_fr, content_ru = await _generate_content(req.category, req.raw_payload)
        except Exception as e:
            logger.error(f"[queue] Generate error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async with get_db() as db:
        # Determine next queue_order for this category
        cursor = await db.execute(
            "SELECT COALESCE(MAX(queue_order), 0) + 1 FROM content_queue WHERE category = ?",
            (req.category,)
        )
        row = await cursor.fetchone()
        next_order = row[0]

        cursor = await db.execute(
            """INSERT INTO content_queue (category, source_url, raw_payload, content_fr, content_ru, queue_order)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (req.category, req.source_url, json.dumps(req.raw_payload), content_fr, content_ru, next_order),
        )
        await db.commit()
        item_id = cursor.lastrowid

    return {"ok": True, "id": item_id, "queue_order": next_order, "category": req.category, "generated": req.generate_now}


@router.get("")
async def list_queue(category: Optional[str] = None, status: Optional[str] = None, limit: int = 100):
    """List queue items, optionally filtered by category and status."""
    query = "SELECT id, category, source_url, queue_order, status, sent_wa_fr, sent_wa_ru, created_at, sent_at, content_fr, content_ru FROM content_queue WHERE 1=1"
    params = []
    if category:
        query += " AND category = ?"
        params.append(category)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY category, queue_order ASC LIMIT ?"
    params.append(limit)

    async with get_db() as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

    return {"items": [dict(r) for r in rows], "total": len(rows)}


@router.get("/stats")
async def queue_stats():
    """Count pending/sent items per category."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT category, status, COUNT(*) as cnt FROM content_queue GROUP BY category, status ORDER BY category"
        )
        rows = await cursor.fetchall()
    return {"stats": [dict(r) for r in rows]}


@router.post("/send/{category}")
async def send_next_from_queue(category: str):
    """Send the next pending item for a category to WhatsApp groups."""
    if category not in PROMPTS:
        raise HTTPException(status_code=400, detail=f"Unknown category '{category}'")

    job_key_map = {
        "guide": "queue_send_guide",
        "droits": "queue_send_droits",
        "prestataire": "queue_send_prestataire",
        "kids": "queue_send_kids",
        "pharma": "queue_send_pharma",
        "supermarket": "queue_send_supermarket",
    }
    async with get_db() as db:
        job_key = job_key_map.get(category)
        if job_key:
            cur = await db.execute(
                "SELECT value FROM settings WHERE key = ?",
                (f"auto_publish_job_{job_key}",)
            )
            row = await cur.fetchone()
            if row and row[0] == "false":
                return {"status": "skipped", "reason": "auto-publish disabled for this job"}

        cursor = await db.execute(
            """SELECT * FROM content_queue WHERE category = ? AND status = 'pending'
               ORDER BY queue_order ASC LIMIT 1""",
            (category,)
        )
        row = await cursor.fetchone()

    if not row:
        return {"status": "empty", "category": category, "message": "No pending items in queue"}

    item = dict(row)

    if not item.get("content_fr") or not item.get("content_ru"):
        # Generate now if content missing
        try:
            payload = json.loads(item["raw_payload"] or "{}")
            content_fr, content_ru = await _generate_content(category, payload)
            async with get_db() as db:
                await db.execute(
                    "UPDATE content_queue SET content_fr=?, content_ru=? WHERE id=?",
                    (content_fr, content_ru, item["id"])
                )
                await db.commit()
            item["content_fr"] = content_fr
            item["content_ru"] = content_ru
        except Exception as e:
            return {"status": "error", "reason": f"Content generation failed: {e}"}

    errors = []
    sent_fr = sent_ru = False

    img_fr = CATEGORY_IMAGES_FR.get(category)
    img_ru = CATEGORY_IMAGES_RU.get(category)

    if WHAPI_TOKEN and WHAPI_GROUP_FR and item.get("content_fr"):
        try:
            await _whapi_send(WHAPI_GROUP_FR, item["content_fr"], img_fr)
            sent_fr = True
        except Exception as e:
            errors.append(f"FR: {e}")

    if WHAPI_TOKEN and WHAPI_GROUP_RU and item.get("content_ru"):
        try:
            await _whapi_send(WHAPI_GROUP_RU, item["content_ru"], img_ru)
            sent_ru = True
        except Exception as e:
            errors.append(f"RU: {e}")

    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        await db.execute(
            """UPDATE content_queue SET status='sent', sent_wa_fr=?, sent_wa_ru=?, sent_at=?
               WHERE id=?""",
            (1 if sent_fr else 0, 1 if sent_ru else 0, now, item["id"])
        )
        await db.commit()

    return {
        "status": "sent",
        "category": category,
        "queue_order": item["queue_order"],
        "sent_fr": sent_fr,
        "sent_ru": sent_ru,
        "errors": errors,
    }


class QueueEditBody(BaseModel):
    content_fr: Optional[str] = None
    content_ru: Optional[str] = None


@router.patch("/{item_id}")
async def edit_queue_item(item_id: int, body: QueueEditBody):
    """Update FR and/or RU content of a pending queue item."""
    async with get_db() as db:
        cursor = await db.execute("SELECT status FROM content_queue WHERE id = ?", (item_id,))
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if row["status"] != "pending":
        raise HTTPException(status_code=400, detail="Only pending items can be edited")
    updates, params = [], []
    if body.content_fr is not None:
        updates.append("content_fr = ?")
        params.append(body.content_fr)
    if body.content_ru is not None:
        updates.append("content_ru = ?")
        params.append(body.content_ru)
    if not updates:
        return {"ok": True, "changed": 0}
    params.append(item_id)
    async with get_db() as db:
        await db.execute(f"UPDATE content_queue SET {', '.join(updates)} WHERE id = ?", params)
        await db.commit()
    return {"ok": True, "changed": len(updates)}


@router.delete("/{item_id}")
async def delete_queue_item(item_id: int):
    """Delete a queue item (e.g., to re-order or remove bad content)."""
    async with get_db() as db:
        await db.execute("DELETE FROM content_queue WHERE id = ?", (item_id,))
        await db.commit()
    return {"ok": True}


@router.get("/{item_id}")
async def get_queue_item(item_id: int):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM content_queue WHERE id = ?", (item_id,))
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return dict(row)
