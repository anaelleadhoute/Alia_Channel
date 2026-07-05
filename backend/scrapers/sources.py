"""
All RSS/scraping sources with their language routing.
language: 'fr' → AL.IA FR group only
          'ru' → AL.IA RU group only
          'both' → both groups (translated separately by AI)
"""

SOURCES = [
    # ─── French sources ───────────────────────────────────────────────
    {
        "name": "i24news FR",
        "url": "https://www.i24news.tv/fr/rss",
        "type": "rss",
        "language": "fr",
    },
    {
        "name": "JForum",
        "url": "https://www.jforum.fr/feed",
        "type": "rss",
        "language": "fr",
    },

    # ─── Russian sources ──────────────────────────────────────────────
    {
        "name": "i24news RU",
        "url": "https://www.i24news.tv/ru/rss",
        "type": "rss",
        "language": "ru",
    },

    # ─── English/Hebrew → AI translates to FR + RU ────────────────────
    {
        "name": "Times of Israel",
        "url": "https://www.timesofisrael.com/feed/",
        "type": "rss",
        "language": "both",
    },
    {
        "name": "Jerusalem Post",
        "url": "https://www.jpost.com/rss/rssfeedsisraelnews.aspx",
        "type": "rss",
        "language": "both",
    },
    {
        "name": "Ynet News",
        "url": "https://www.ynet.co.il/Integration/StoryRss2.xml",
        "type": "rss",
        "language": "both",
    },
    {
        "name": "Israel Hayom",
        "url": "https://www.israelhayom.co.il/rss.xml",
        "type": "rss",
        "language": "both",
    },
    {
        "name": "Walla News",
        "url": "https://rss.walla.co.il/feed/1",
        "type": "rss",
        "language": "both",
    },
]

# Kol Zchut — scraped separately on Sunday workflow
KOL_ZCHUT_BASE_URL = "https://www.kolzchut.org.il"
KOL_ZCHUT_PAGES = [
    "/he/עולים_חדשים",
    "/he/דיור",
    "/he/בריאות",
    "/he/עבודה",
]
