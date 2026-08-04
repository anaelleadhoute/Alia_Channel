"""
All RSS/scraping sources with their language routing.
language: 'fr' → AL.IA FR group only
          'ru' → AL.IA RU group only
          'both' → both groups (translated separately by AI)
"""

SOURCES = [
    {
        "name": "Jerusalem Post",
        "url": "https://www.jpost.com/rss/rssfeedsisraelnews.aspx",
        "type": "rss",
        "language": "both",
    },
    {
        "name": "Jerusalem Post - Iran",
        "url": "https://www.jpost.com/middle-east/iran-news",
        "base_url": "https://www.jpost.com",
        "type": "html",
        "language": "both",
    },
    {
        "name": "Jerusalem Post - Defense",
        "url": "https://www.jpost.com/israel-news/defense-news",
        "base_url": "https://www.jpost.com",
        "type": "html",
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
