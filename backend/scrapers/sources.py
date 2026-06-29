"""
All RSS/scraping sources with their language routing.
language: 'fr' → AL.IA FR group only
          'ru' → AL.IA RU group only
          'both' → both groups (translated separately by AI)
"""

SOURCES = [
    # ─── French sources ───────────────────────────────────────────────
    {
        "name": "Times of Israel FR",
        "url": "https://fr.timesofisrael.com/feed/",
        "type": "rss",
        "language": "fr",
    },
    {
        "name": "i24news FR",
        "url": "https://www.i24news.tv/fr/rss",
        "type": "rss",
        "language": "fr",
    },
    {
        "name": "JForum",
        "url": "https://www.jforum.fr/feed/",
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

    # ─── Both groups (AI translates to FR + RU) ───────────────────────
    {
        "name": "Misrad Haaliya",
        "url": "https://www.gov.il/he/api/DataGovProxy/GetOdataRss?RssUrl=he/rss/ministryofaliyanabsorption",
        "type": "rss",
        "language": "both",
    },
    {
        "name": "Bituach Leumi",
        "url": "https://www.btl.gov.il/rss/Pages/rss.aspx",
        "type": "rss",
        "language": "both",
    },
    {
        "name": "Gov IL",
        "url": "https://www.gov.il/he/api/DataGovProxy/GetOdataRss?RssUrl=he/rss/govil",
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
