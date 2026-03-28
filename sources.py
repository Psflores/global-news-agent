"""
sources.py — Fuentes RSS globales curadas por región e idioma.

Criterios de selección:
- Cobertura internacional real (no local)
- Diversidad geográfica y lingüística
- Sin sesgos de entretenimiento
- Tier 1 = agencias y medios de referencia global
- Tier 2 = medios regionales serios
- Tier 3 = fuentes especializadas (energía, salud, geopolítica)

Cuota máxima por región: 35% del pool total de artículos.
"""

NEWS_SOURCES = {

    # ─────────────────────────────────────────────────────────────
    # GLOBAL / AGENCIAS
    # ─────────────────────────────────────────────────────────────
    "global": [
        {
            "name": "Reuters - World",
            "url": "https://feeds.reuters.com/reuters/worldNews",
            "language": "en",
            "tier": 1,
            "bias_score": 0.0,  # neutro
            "tags": ["geopolitics", "economy", "conflict"],
        },
        {
            "name": "AP News - Top Headlines",
            "url": "https://feeds.apnews.com/rss/apf-topnews",
            "language": "en",
            "tier": 1,
            "bias_score": 0.0,
            "tags": ["geopolitics", "economy"],
        },
        {
            "name": "AFP - International",
            "url": "https://www.afp.com/en/rss",
            "language": "en",
            "tier": 1,
            "bias_score": 0.0,
            "tags": ["geopolitics", "conflict"],
        },
        {
            "name": "UN News",
            "url": "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
            "language": "en",
            "tier": 1,
            "bias_score": 0.0,
            "tags": ["institutional", "humanitarian", "geopolitics"],
        },
        {
            "name": "Foreign Policy",
            "url": "https://foreignpolicy.com/feed/",
            "language": "en",
            "tier": 2,
            "bias_score": 0.1,
            "tags": ["geopolitics", "strategy"],
        },
        {
            "name": "The Economist - World",
            "url": "https://www.economist.com/international/rss.xml",
            "language": "en",
            "tier": 1,
            "bias_score": 0.1,
            "tags": ["economy", "geopolitics"],
        },
        {
            "name": "Financial Times - World",
            "url": "https://www.ft.com/world?format=rss",
            "language": "en",
            "tier": 1,
            "bias_score": 0.1,
            "tags": ["economy", "markets", "geopolitics"],
        },
    ],

    # ─────────────────────────────────────────────────────────────
    # EUROPA OCCIDENTAL
    # ─────────────────────────────────────────────────────────────
    "europe_west": [
        {
            "name": "BBC News - World",
            "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
            "language": "en",
            "tier": 1,
            "bias_score": 0.1,
            "tags": ["geopolitics", "conflict", "humanitarian"],
        },
        {
            "name": "The Guardian - World",
            "url": "https://www.theguardian.com/world/rss",
            "language": "en",
            "tier": 2,
            "bias_score": 0.3,
            "tags": ["environment", "human_rights", "geopolitics"],
        },
        {
            "name": "Le Monde - International",
            "url": "https://www.lemonde.fr/international/rss_full.xml",
            "language": "fr",
            "tier": 1,
            "bias_score": 0.1,
            "tags": ["geopolitics", "europe", "africa"],
        },
        {
            "name": "Der Spiegel - International",
            "url": "https://www.spiegel.de/international/index.rss",
            "language": "de",
            "tier": 1,
            "bias_score": 0.1,
            "tags": ["geopolitics", "europe", "economy"],
        },
        {
            "name": "El País - Internacional",
            "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada",
            "language": "es",
            "tier": 1,
            "bias_score": 0.1,
            "tags": ["geopolitics", "latin_america", "europe"],
        },
        {
            "name": "Euractiv",
            "url": "https://www.euractiv.com/feed/",
            "language": "en",
            "tier": 2,
            "bias_score": 0.1,
            "tags": ["europe", "institutional", "policy"],
        },
        {
            "name": "NZZ - International",
            "url": "https://www.nzz.ch/international.rss",
            "language": "de",
            "tier": 2,
            "bias_score": 0.1,
            "tags": ["economy", "geopolitics"],
        },
    ],

    # ─────────────────────────────────────────────────────────────
    # EUROPA DEL ESTE / EURASIA
    # ─────────────────────────────────────────────────────────────
    "europe_east": [
        {
            "name": "Kyiv Independent",
            "url": "https://kyivindependent.com/feed/",
            "language": "en",
            "tier": 2,
            "bias_score": 0.4,  # contexto de conflicto activo
            "tags": ["conflict", "europe_east", "russia"],
        },
        {
            "name": "Meduza - English",
            "url": "https://meduza.io/rss/en/all",
            "language": "en",
            "tier": 2,
            "bias_score": 0.3,
            "tags": ["russia", "politics", "europe_east"],
        },
        {
            "name": "Eurasianet",
            "url": "https://eurasianet.org/rss.xml",
            "language": "en",
            "tier": 2,
            "bias_score": 0.1,
            "tags": ["caucasus", "central_asia", "geopolitics"],
        },
        {
            "name": "Balkan Insight",
            "url": "https://balkaninsight.com/feed/",
            "language": "en",
            "tier": 2,
            "bias_score": 0.1,
            "tags": ["balkans", "europe_east", "conflict"],
        },
    ],

    # ─────────────────────────────────────────────────────────────
    # MEDIO ORIENTE Y NORTE DE ÁFRICA
    # ─────────────────────────────────────────────────────────────
    "middle_east_north_africa": [
        {
            "name": "Al Jazeera - English",
            "url": "https://www.aljazeera.com/xml/rss/all.xml",
            "language": "en",
            "tier": 1,
            "bias_score": 0.3,
            "tags": ["middle_east", "conflict", "humanitarian"],
        },
        {
            "name": "Al-Monitor",
            "url": "https://www.al-monitor.com/rss",
            "language": "en",
            "tier": 2,
            "bias_score": 0.1,
            "tags": ["middle_east", "geopolitics"],
        },
        {
            "name": "Haaretz - English",
            "url": "https://www.haaretz.com/cmlink/1.628752",
            "language": "en",
            "tier": 2,
            "bias_score": 0.2,
            "tags": ["israel", "middle_east", "conflict"],
        },
        {
            "name": "Middle East Eye",
            "url": "https://www.middleeasteye.net/rss",
            "language": "en",
            "tier": 2,
            "bias_score": 0.3,
            "tags": ["middle_east", "conflict", "politics"],
        },
        {
            "name": "Arab News",
            "url": "https://www.arabnews.com/rss.xml",
            "language": "en",
            "tier": 2,
            "bias_score": 0.3,
            "tags": ["gulf", "economy", "politics"],
        },
    ],

    # ─────────────────────────────────────────────────────────────
    # ASIA - PACÍFICO
    # ─────────────────────────────────────────────────────────────
    "asia_pacific": [
        {
            "name": "South China Morning Post - World",
            "url": "https://www.scmp.com/rss/91/feed",
            "language": "en",
            "tier": 1,
            "bias_score": 0.2,
            "tags": ["china", "east_asia", "economy", "geopolitics"],
        },
        {
            "name": "NHK World - Asia-Pacific",
            "url": "https://www3.nhk.or.jp/rss/news/cat0.xml",
            "language": "en",
            "tier": 1,
            "bias_score": 0.1,
            "tags": ["japan", "east_asia", "geopolitics"],
        },
        {
            "name": "The Hindu - International",
            "url": "https://www.thehindu.com/news/international/feeder/default.rss",
            "language": "en",
            "tier": 2,
            "bias_score": 0.1,
            "tags": ["india", "south_asia", "geopolitics"],
        },
        {
            "name": "The Straits Times - Asia",
            "url": "https://www.straitstimes.com/news/asia/rss.xml",
            "language": "en",
            "tier": 2,
            "bias_score": 0.1,
            "tags": ["southeast_asia", "economy", "geopolitics"],
        },
        {
            "name": "Nikkei Asia",
            "url": "https://asia.nikkei.com/rss/feed/nar",
            "language": "en",
            "tier": 1,
            "bias_score": 0.1,
            "tags": ["japan", "east_asia", "economy", "markets"],
        },
        {
            "name": "The Diplomat",
            "url": "https://thediplomat.com/feed/",
            "language": "en",
            "tier": 2,
            "bias_score": 0.1,
            "tags": ["asia_pacific", "geopolitics", "strategy"],
        },
        {
            "name": "Global Times - EN (China State Media, señal)",
            "url": "https://www.globaltimes.cn/rss/outbrain.xml",
            "language": "en",
            "tier": 3,
            "bias_score": 0.8,  # incluir solo como señal, no como fuente fiable
            "tags": ["china", "state_media"],
            "use_as_signal_only": True,
        },
    ],

    # ─────────────────────────────────────────────────────────────
    # ÁFRICA SUB-SAHARIANA
    # ─────────────────────────────────────────────────────────────
    "africa_sub_saharan": [
        {
            "name": "AllAfrica",
            "url": "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
            "language": "en",
            "tier": 2,
            "bias_score": 0.1,
            "tags": ["africa", "geopolitics", "humanitarian"],
        },
        {
            "name": "Daily Maverick",
            "url": "https://www.dailymaverick.co.za/feed/",
            "language": "en",
            "tier": 2,
            "bias_score": 0.2,
            "tags": ["south_africa", "africa", "politics"],
        },
        {
            "name": "The East African",
            "url": "https://www.theeastafrican.co.ke/rss/",
            "language": "en",
            "tier": 2,
            "bias_score": 0.1,
            "tags": ["east_africa", "economy", "geopolitics"],
        },
        {
            "name": "Jeune Afrique",
            "url": "https://www.jeuneafrique.com/feed/",
            "language": "fr",
            "tier": 2,
            "bias_score": 0.2,
            "tags": ["francophone_africa", "politics", "economy"],
        },
    ],

    # ─────────────────────────────────────────────────────────────
    # AMÉRICAS
    # ─────────────────────────────────────────────────────────────
    "americas": [
        {
            "name": "NPR - World",
            "url": "https://feeds.npr.org/1004/rss.xml",
            "language": "en",
            "tier": 2,
            "bias_score": 0.2,
            "tags": ["usa", "geopolitics", "humanitarian"],
        },
        {
            "name": "Folha de S.Paulo - Mundo",
            "url": "https://feeds.folha.uol.com.br/mundo/rss091.xml",
            "language": "pt",
            "tier": 2,
            "bias_score": 0.1,
            "tags": ["brazil", "latin_america", "geopolitics"],
        },
        {
            "name": "La Nación - Mundo",
            "url": "https://www.lanacion.com.ar/arc/outboundfeeds/rss/categoria/el-mundo/",
            "language": "es",
            "tier": 2,
            "bias_score": 0.2,
            "tags": ["argentina", "latin_america", "geopolitics"],
        },
        {
            "name": "NACLA Report",
            "url": "https://nacla.org/rss.xml",
            "language": "en",
            "tier": 3,
            "bias_score": 0.4,
            "tags": ["latin_america", "politics", "human_rights"],
        },
    ],

    # ─────────────────────────────────────────────────────────────
    # FUENTES ESPECIALIZADAS TEMÁTICAS
    # ─────────────────────────────────────────────────────────────
    "specialized": [
        {
            "name": "IAEA - Nuclear Safety",
            "url": "https://www.iaea.org/feeds/topical/nuclear-safety",
            "language": "en",
            "tier": 1,
            "bias_score": 0.0,
            "tags": ["nuclear", "security", "institutional"],
        },
        {
            "name": "WHO - News",
            "url": "https://www.who.int/rss-feeds/news-english.xml",
            "language": "en",
            "tier": 1,
            "bias_score": 0.0,
            "tags": ["health", "pandemic", "institutional"],
        },
        {
            "name": "OPEC - News",
            "url": "https://www.opec.org/opec_web/en/press_room/all.htm",  # scraping
            "language": "en",
            "tier": 1,
            "bias_score": 0.1,
            "tags": ["energy", "oil", "economy"],
        },
        {
            "name": "IMF - News",
            "url": "https://www.imf.org/en/News/rss?language=eng",
            "language": "en",
            "tier": 1,
            "bias_score": 0.0,
            "tags": ["economy", "financial_crisis", "institutional"],
        },
        {
            "name": "Devex - World Development",
            "url": "https://www.devex.com/news.rss",
            "language": "en",
            "tier": 2,
            "bias_score": 0.1,
            "tags": ["humanitarian", "development", "institutional"],
        },
        {
            "name": "Crisis Group - Reports",
            "url": "https://www.crisisgroup.org/rss.xml",
            "language": "en",
            "tier": 2,
            "bias_score": 0.0,
            "tags": ["conflict", "geopolitics", "security"],
        },
        {
            "name": "Bellingcat - Investigations",
            "url": "https://www.bellingcat.com/feed/",
            "language": "en",
            "tier": 2,
            "bias_score": 0.1,
            "tags": ["conflict", "investigation", "security"],
        },
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE CUOTAS REGIONALES
# Ninguna región puede aportar más del REGIONAL_CAP del pool total
# ─────────────────────────────────────────────────────────────────────────────

REGIONAL_CAPS = {
    "global": 0.40,               # Agencias globales tienen cap más alto
    "europe_west": 0.35,
    "europe_east": 0.25,
    "middle_east_north_africa": 0.25,
    "asia_pacific": 0.35,
    "africa_sub_saharan": 0.20,
    "americas": 0.35,
    "specialized": 0.20,
}

# Regiones consideradas "anglosajonas" — se aplica penalización si dominan
ANGLOPHONE_REGIONS = {"europe_west", "americas", "global"}

# Umbral: si regiones anglófonas aportan >60% del pool, activar penalización
ANGLOCENTRIC_THRESHOLD = 0.60


def get_all_sources() -> list[dict]:
    """Retorna lista plana de todas las fuentes con su región anotada."""
    sources = []
    for region, feeds in NEWS_SOURCES.items():
        for feed in feeds:
            feed_with_region = feed.copy()
            feed_with_region["region"] = region
            sources.append(feed_with_region)
    return sources


def get_sources_by_tier(max_tier: int = 2) -> list[dict]:
    """Retorna solo fuentes hasta el tier especificado."""
    return [s for s in get_all_sources() if s.get("tier", 3) <= max_tier]


def get_sources_by_topic(tag: str) -> list[dict]:
    """Retorna fuentes que cubren un tópico específico."""
    return [s for s in get_all_sources() if tag in s.get("tags", [])]
