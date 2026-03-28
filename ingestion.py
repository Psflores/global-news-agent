"""
ingestion.py — Fetching, parsing y normalización de artículos.

Pipeline:
1. Fetch RSS feeds (feedparser)
2. Scrape artículo completo si el feed trae solo resumen (newspaper4k)
3. Normalizar: título, URL, fecha UTC, idioma, texto, entidades
4. Fingerprint con SHA-256 para deduplicación exacta
5. Aplicar cuotas regionales para evitar sesgo de fuente
"""

import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse

import feedparser
import langdetect

# newspaper4k — import lazy para evitar error lxml en Python 3.9
try:
    from newspaper import Article as NewspaperArticle
    _NEWSPAPER_OK = True
except ImportError:
    _NEWSPAPER_OK = False
    NewspaperArticle = None

from sources import get_all_sources, REGIONAL_CAPS, ANGLOPHONE_REGIONS, ANGLOCENTRIC_THRESHOLD

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

MAX_ARTICLE_AGE_HOURS = 24       # Ignorar artículos más viejos de 24h
MIN_ARTICLE_WORDS = 80           # Ignorar artículos con <80 palabras
MAX_WORKERS = 12                 # Threads paralelos para fetching
REQUEST_TIMEOUT = 15             # Segundos por request
MAX_ARTICLES_PER_SOURCE = 30     # Límite por fuente individual


# ─────────────────────────────────────────────────────────────────────────────
# MODELO DE DATOS — Artículo normalizado
# ─────────────────────────────────────────────────────────────────────────────

class Article:
    def __init__(self):
        self.id: str = ""                  # SHA-256 fingerprint
        self.title: str = ""
        self.url: str = ""
        self.source_name: str = ""
        self.source_region: str = ""
        self.source_tier: int = 3
        self.source_bias: float = 0.0
        self.language: str = "en"
        self.published_at: Optional[datetime] = None
        self.ingested_at: datetime = datetime.now(timezone.utc)
        self.summary: str = ""
        self.full_text: str = ""
        self.word_count: int = 0
        self.entities: dict = {
            "countries": [],
            "organizations": [],
            "people": [],
            "topics": [],
        }
        self.tags: list = []
        self.embedding: Optional[list] = None  # Llenado en clusterer.py
        self.use_as_signal_only: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source_name": self.source_name,
            "source_region": self.source_region,
            "source_tier": self.source_tier,
            "language": self.language,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "ingested_at": self.ingested_at.isoformat(),
            "summary": self.summary[:500],  # Truncar para output limpio
            "word_count": self.word_count,
            "entities": self.entities,
            "tags": self.tags,
        }

    def __repr__(self):
        return f"<Article [{self.source_name}] '{self.title[:60]}...'>"


# ─────────────────────────────────────────────────────────────────────────────
# FETCHING DE RSS
# ─────────────────────────────────────────────────────────────────────────────

def fetch_rss_feed(source: dict) -> list[Article]:
    """
    Parsea un feed RSS y retorna lista de artículos normalizados.
    Usa feedparser como base; opcionalmente hace scraping con newspaper4k.
    """
    articles = []

    try:
        feed = feedparser.parse(
            source["url"],
            request_headers={
                "User-Agent": "GlobalNewsAgent/1.0 (research; contact@example.com)",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

        if feed.bozo and not feed.entries:
            logger.warning(f"Feed inválido o vacío: {source['name']}")
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_ARTICLE_AGE_HOURS)
        count = 0

        for entry in feed.entries:
            if count >= MAX_ARTICLES_PER_SOURCE:
                break

            # ── PRE-FILTRO de fecha: cortar artículos viejos ANTES de parsear ──
            # Evita que feeds con cientos de artículos históricos (Economist, FT)
            # disparen conexiones o scraping innecesario.
            entry_date = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    entry_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                try:
                    entry_date = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            if entry_date and entry_date < cutoff:
                continue  # Artículo viejo — saltear sin procesar

            article = _parse_rss_entry(entry, source)
            if article is None:
                continue

            # Filtro secundario por antigüedad (para entradas sin fecha en el feed)
            if article.published_at and article.published_at < cutoff:
                continue

            articles.append(article)
            count += 1

        logger.info(f"[{source['name']}] → {len(articles)} artículos fetched")

    except Exception as e:
        logger.error(f"Error fetching {source['name']}: {e}")

    return articles


def _parse_rss_entry(entry: feedparser.FeedParserDict, source: dict) -> Optional[Article]:
    """Convierte un entry de feedparser en un Article normalizado."""
    try:
        article = Article()
        article.source_name = source["name"]
        article.source_region = source.get("region", "unknown")
        article.source_tier = source.get("tier", 3)
        article.source_bias = source.get("bias_score", 0.5)
        article.tags = source.get("tags", [])
        article.use_as_signal_only = source.get("use_as_signal_only", False)

        # Título
        article.title = getattr(entry, "title", "").strip()
        if not article.title:
            return None

        # URL
        article.url = getattr(entry, "link", "").strip()
        if not article.url:
            return None

        # Fecha de publicación
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            article.published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            article.published_at = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        else:
            article.published_at = datetime.now(timezone.utc)

        # Resumen (del feed)
        summary = ""
        if hasattr(entry, "summary"):
            summary = entry.summary
        elif hasattr(entry, "description"):
            summary = entry.description
        article.summary = _clean_html(summary)[:1000]

        # Texto completo: intentar extraer con newspaper4k si summary es corto
        if len(article.summary.split()) < MIN_ARTICLE_WORDS:
            full_text = _scrape_article_text(article.url)
            if full_text:
                article.full_text = full_text
                article.word_count = len(full_text.split())
                if not article.summary:
                    article.summary = full_text[:500]
        else:
            article.full_text = article.summary
            article.word_count = len(article.summary.split())

        # Filtrar artículos demasiado cortos
        if article.word_count < MIN_ARTICLE_WORDS:
            return None

        # Idioma
        try:
            text_sample = f"{article.title} {article.summary}"
            article.language = langdetect.detect(text_sample)
        except Exception:
            article.language = source.get("language", "en")

        # Fingerprint SHA-256 (título + dominio) para dedup exacta
        domain = urlparse(article.url).netloc
        fingerprint_text = f"{article.title.lower().strip()}{domain}"
        article.id = hashlib.sha256(fingerprint_text.encode()).hexdigest()[:16]

        return article

    except Exception as e:
        logger.debug(f"Error parseando entry: {e}")
        return None


def _scrape_article_text(url: str) -> str:
    """
    Extrae texto completo de un artículo.
    Si LADDER_URL está configurado, usa Ladder como proxy para bypasear paywalls.
    Si no, usa newspaper4k directamente.

    Ladder (github.com/everywall/ladder) es un proxy auto-hosteado:
    - Instalación: docker run -p 8080:8080 ghcr.io/everywall/ladder:latest
    - Luego configurar LADDER_URL = "http://localhost:8080"
    """
    import os
    ladder_url = os.environ.get("LADDER_URL", "").rstrip("/")

    if not _NEWSPAPER_OK:
        return ""

    if ladder_url:
        try:
            import requests
            proxied_url = f"{ladder_url}/{url}"
            resp = requests.get(proxied_url, timeout=REQUEST_TIMEOUT, headers={
                "User-Agent": "GlobalNewsAgent/1.0"
            })
            if resp.ok and len(resp.text) > 200:
                # Parsear HTML con newspaper4k
                news_article = NewspaperArticle(url)
                news_article.set_html(resp.text)
                news_article.parse()
                if news_article.text:
                    return news_article.text
        except Exception as e:
            logger.debug(f"Ladder falló para {url}: {e}")

    # Fallback: newspaper4k directo
    try:
        news_article = NewspaperArticle(url)
        news_article.download()
        news_article.parse()
        return news_article.text
    except Exception:
        return ""


def _clean_html(text: str) -> str:
    """
    Limpieza profunda de texto proveniente de RSS/HTML.
    Elimina tags, entidades HTML, artefactos de CMS y metadatos de feed.
    """
    import re, html

    # 1. Decodificar entidades HTML (&nbsp; → espacio, &amp; → &, etc.)
    text = html.unescape(text)

    # 2. Eliminar tags HTML
    text = re.sub(r"<[^>]+>", " ", text)

    # 3. Eliminar patrones típicos de CMS (bylines, timestamps, etc.)
    # "Submitted by X on Sat, 03/28/2026" o "Submitted by on"
    text = re.sub(r"Submitted by\s*.*?on\s+\w+,\s*\d{2}/\d{2}/\d{4}[-–\s]*\d{2}:\d{2}", "", text, flags=re.IGNORECASE)
    text = re.sub(r"Submitted by\s+on\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"Submitted by\s+[A-Za-z\s]{0,40}on\s*", "", text, flags=re.IGNORECASE)
    # "By Author Name |" o "By Author Name -"
    text = re.sub(r"\bBy\s+[A-Z][a-z]+ [A-Z][a-z]+\s*[|\-]", "", text)
    # Timestamps estilo "Sat, 03/28/2026 - 12:48"
    text = re.sub(r"\w+,\s*\d{2}/\d{2}/\d{4}\s*[-–]\s*\d{2}:\d{2}", "", text)
    # "MEE staff", "AFP staff", etc.
    text = re.sub(r"\b(MEE|AFP|AP|Reuters|BBC)\s+staff\b", "", text, flags=re.IGNORECASE)
    # "Off An" y otros residuos de navegación
    text = re.sub(r"\bOff An?\b", "", text)

    # 4. Eliminar espacios múltiples y líneas vacías
    text = re.sub(r"\s{3,}", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)

    # 5. Limpiar caracteres extraños remanentes
    text = re.sub(r"[\xa0\u200b\u200c\u200d\ufeff]", " ", text)  # non-breaking spaces etc.
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# INGESTA PARALELA DE TODAS LAS FUENTES
# ─────────────────────────────────────────────────────────────────────────────

def ingest_all_sources(max_tier: int = 2, verbose: bool = True) -> list[Article]:
    """
    Fetcha todas las fuentes en paralelo y aplica cuotas regionales.
    Retorna lista de artículos normalizados, deduplicados por fingerprint exacto.
    """
    sources = [s for s in get_all_sources() if s.get("tier", 3) <= max_tier]

    if verbose:
        logger.info(f"Iniciando ingesta: {len(sources)} fuentes")

    # Fetch paralelo
    all_articles: list[Article] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_rss_feed, source): source for source in sources}
        for future in as_completed(futures):
            try:
                articles = future.result(timeout=REQUEST_TIMEOUT + 5)
                all_articles.extend(articles)
            except Exception as e:
                source = futures[future]
                logger.error(f"Timeout/error en {source['name']}: {e}")

    # Deduplicación exacta por fingerprint
    seen_ids = set()
    unique_articles = []
    for article in all_articles:
        if article.id not in seen_ids:
            seen_ids.add(article.id)
            unique_articles.append(article)

    if verbose:
        logger.info(f"Artículos únicos tras dedup exacta: {len(unique_articles)}/{len(all_articles)}")

    # Aplicar cuotas regionales
    final_articles = _apply_regional_caps(unique_articles, verbose)

    # Verificar sesgo anglocéntrico
    _check_anglocentrism(final_articles, verbose)

    return final_articles


def _apply_regional_caps(articles: list[Article], verbose: bool) -> list[Article]:
    """
    Aplica cuotas máximas por región para garantizar diversidad geográfica.
    Si una región supera su cap, descarta los artículos de menor tier.
    """
    total = len(articles)
    by_region: dict[str, list[Article]] = {}

    for article in articles:
        region = article.source_region
        by_region.setdefault(region, []).append(article)

    capped_articles = []

    for region, region_articles in by_region.items():
        cap = REGIONAL_CAPS.get(region, 0.35)
        max_count = int(total * cap)

        if len(region_articles) > max_count:
            # Priorizar por tier y luego por bias score (menor = mejor)
            region_articles.sort(key=lambda a: (a.source_tier, a.source_bias))
            region_articles = region_articles[:max_count]
            if verbose:
                logger.info(f"Región '{region}' recortada a {max_count} artículos (cap {cap:.0%})")

        capped_articles.extend(region_articles)

    return capped_articles


def _check_anglocentrism(articles: list[Article], verbose: bool):
    """Verifica y registra si el pool tiene sesgo anglocéntrico excesivo."""
    total = len(articles)
    if total == 0:
        return

    anglophone_count = sum(
        1 for a in articles if a.source_region in ANGLOPHONE_REGIONS
    )
    ratio = anglophone_count / total

    if ratio > ANGLOCENTRIC_THRESHOLD:
        logger.warning(
            f"⚠️  SESGO ANGLOCÉNTRICO DETECTADO: {ratio:.0%} del pool es de "
            f"regiones anglófonas (umbral: {ANGLOCENTRIC_THRESHOLD:.0%}). "
            f"Considera agregar más fuentes no anglófonas."
        )
    elif verbose:
        logger.info(f"Diversidad OK: {ratio:.0%} de fuentes anglófonas en el pool")


# ─────────────────────────────────────────────────────────────────────────────
# ENRIQUECIMIENTO POST-SCORING — Solo para el top N
# ─────────────────────────────────────────────────────────────────────────────

def enrich_top_articles(top_results: list, timeout_per_article: int = 8) -> list:
    """
    Para los artículos del top 5, intenta hacer scraping del texto completo.
    Solo se aplica si el resumen es corto (<100 palabras).
    Usa threads paralelos con timeout estricto para no bloquear el pipeline.

    top_results: lista de (cluster, breakdown) del scorer
    """
    def enrich_one(cluster_tuple):
        cluster, breakdown = cluster_tuple
        rep = cluster.representative_article
        if rep is None:
            return cluster_tuple

        # Solo enriquecer si el resumen es corto
        if rep.word_count >= 100:
            return cluster_tuple

        logger.info(f"Enriqueciendo: {rep.title[:50]}...")
        full_text = _scrape_article_text(rep.url)

        if full_text and len(full_text.split()) > rep.word_count:
            rep.full_text = full_text[:3000]
            rep.summary = _clean_html(full_text[:1500])
            rep.word_count = len(full_text.split())
            logger.info(f"  ✓ {rep.word_count} palabras obtenidas")

        return cluster_tuple

    logger.info(f"Enriqueciendo {len(top_results)} artículos del top con scraping...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(enrich_one, ct) for ct in top_results]
        enriched = []
        for future in as_completed(futures):
            try:
                enriched.append(future.result(timeout=timeout_per_article + 2))
            except Exception:
                pass

    # Reordenar por rank original
    return top_results  # El enriquecimiento es in-place sobre los objetos Article


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES DE INSPECCIÓN
# ─────────────────────────────────────────────────────────────────────────────

def print_ingestion_stats(articles: list[Article]):
    """Imprime estadísticas del pool de artículos ingresados."""
    from collections import Counter

    print(f"\n{'='*60}")
    print(f"ESTADÍSTICAS DE INGESTA — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")
    print(f"Total artículos: {len(articles)}")

    region_counts = Counter(a.source_region for a in articles)
    print(f"\nDistribución por región:")
    for region, count in sorted(region_counts.items(), key=lambda x: -x[1]):
        pct = count / len(articles) * 100
        print(f"  {region:<35} {count:>4} ({pct:.1f}%)")

    lang_counts = Counter(a.language for a in articles)
    print(f"\nDistribución por idioma:")
    for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1])[:10]:
        pct = count / len(articles) * 100
        print(f"  {lang:<10} {count:>4} ({pct:.1f}%)")

    tier_counts = Counter(a.source_tier for a in articles)
    print(f"\nDistribución por tier:")
    for tier, count in sorted(tier_counts.items()):
        pct = count / len(articles) * 100
        print(f"  Tier {tier}:    {count:>4} ({pct:.1f}%)")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print("Iniciando ingesta de prueba...")
    articles = ingest_all_sources(max_tier=2, verbose=True)
    print_ingestion_stats(articles)
    print(f"\nEjemplo de artículo:")
    if articles:
        import json
        print(json.dumps(articles[0].to_dict(), indent=2, ensure_ascii=False))
