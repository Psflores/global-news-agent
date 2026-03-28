"""
clusterer.py — Deduplicación semántica y clustering de artículos por evento.

Estrategia en dos pasos:
1. Deduplicación near-duplicate: MinHash LSH (rápido, O(n) efectivo)
2. Clustering por evento: sentence-transformers embeddings + DBSCAN

El resultado son clusters donde cada uno representa UN evento distinto
del mundo real, con múltiples artículos de distintas fuentes.

Principio central: un evento con 30 artículos de 15 medios distintos
es MÁS IMPORTANTE que un evento con 50 artículos pero de 3 medios.
"""

import logging
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Importaciones condicionales (pueden fallar si las libs no están instaladas)
try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    logger.warning("sentence-transformers no disponible. Usando TF-IDF fallback.")

try:
    from sklearn.cluster import DBSCAN
    from sklearn.metrics.pairwise import cosine_similarity
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    logger.warning("scikit-learn no disponible.")

try:
    from datasketch import MinHash, MinHashLSH
    HAS_DATASKETCH = True
except ImportError:
    HAS_DATASKETCH = False
    logger.warning("datasketch no disponible. Usando dedup por Jaccard básica.")

# Modelo multilingual — funciona en 100+ idiomas sin traducción
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# ─────────────────────────────────────────────────────────────────────────────
# PARÁMETROS DE CLUSTERING
# ─────────────────────────────────────────────────────────────────────────────

MINHASH_THRESHOLD = 0.85      # Similitud para near-duplicate (mismo artículo)
MINHASH_NUM_PERM = 128        # Permutaciones MinHash (más = más preciso)
DBSCAN_EPS = 0.35             # Radio DBSCAN (cosine distance): 0.35 ≈ sim > 0.65
DBSCAN_MIN_SAMPLES = 2        # Mínimo 2 artículos para formar un cluster
MAX_CLUSTER_SIZE = 100        # Cap para evitar mega-clusters


# ─────────────────────────────────────────────────────────────────────────────
# MODELO DE DATOS — Cluster/Evento
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EventCluster:
    cluster_id: str = ""
    event_label: str = ""
    article_ids: list = field(default_factory=list)
    articles: list = field(default_factory=list)   # Lista de Article objects
    article_count: int = 0
    unique_sources: int = 0
    unique_regions: int = 0
    regions: list = field(default_factory=list)
    representative_article: object = None   # El artículo más representativo
    first_seen: Optional[datetime] = None
    centroid_embedding: Optional[np.ndarray] = None
    is_noise: bool = False           # DBSCAN ruido = evento no agrupado
    days_active: int = 1             # Persistencia del evento

    def to_dict(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "event_label": self.event_label,
            "article_count": self.article_count,
            "unique_sources": self.unique_sources,
            "unique_regions": self.unique_regions,
            "regions": self.regions,
            "representative_article": (
                self.representative_article.to_dict()
                if self.representative_article else None
            ),
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "days_active": self.days_active,
        }


# ─────────────────────────────────────────────────────────────────────────────
# PASO 1: DEDUPLICACIÓN NEAR-DUPLICATE (MinHash LSH)
# ─────────────────────────────────────────────────────────────────────────────

def deduplicate_minhash(articles: list) -> list:
    """
    Elimina artículos near-duplicados usando MinHash LSH.
    Retiene el artículo de mayor tier (menor número = mejor fuente).
    """
    if not HAS_DATASKETCH:
        return _deduplicate_jaccard_fallback(articles)

    lsh = MinHashLSH(threshold=MINHASH_THRESHOLD, num_perm=MINHASH_NUM_PERM)
    minhashes = {}

    for article in articles:
        text = _get_shingles_text(article)
        minhash = _compute_minhash(text)
        minhashes[article.id] = minhash

    # Agrupar near-duplicados
    duplicate_groups: dict[str, list] = {}   # id_maestro → [ids duplicados]
    processed = set()

    for article in articles:
        if article.id in processed:
            continue

        minhash = minhashes[article.id]
        try:
            lsh.insert(article.id, minhash)
        except ValueError:
            pass  # Ya insertado

        similar = lsh.query(minhash)
        similar = [s for s in similar if s != article.id and s not in processed]

        if similar:
            duplicate_groups[article.id] = similar
            processed.update(similar)

        processed.add(article.id)

    # Retener solo el artículo de mejor tier de cada grupo
    id_to_article = {a.id: a for a in articles}
    kept_ids = set()
    removed_ids = set()

    for master_id, dup_ids in duplicate_groups.items():
        group = [master_id] + dup_ids
        group_articles = [id_to_article[aid] for aid in group if aid in id_to_article]
        # Ordenar: tier más bajo primero (1 = mejor), luego bias más bajo
        best = sorted(group_articles, key=lambda a: (a.source_tier, a.source_bias))[0]
        kept_ids.add(best.id)
        for a in group_articles:
            if a.id != best.id:
                removed_ids.add(a.id)

    result = [a for a in articles if a.id not in removed_ids]
    logger.info(f"Near-dedup MinHash: {len(articles)} → {len(result)} artículos ({len(removed_ids)} eliminados)")
    return result


def _get_shingles_text(article) -> str:
    """Genera texto para shingles: título + primeras palabras del resumen."""
    title = article.title.lower().strip()
    summary = article.summary[:200].lower().strip()
    return f"{title} {summary}"


def _compute_minhash(text: str) -> "MinHash":
    """Crea un MinHash de un texto usando 3-shingles."""
    minhash = MinHash(num_perm=MINHASH_NUM_PERM)
    words = text.split()
    # 3-word shingles
    for i in range(len(words) - 2):
        shingle = " ".join(words[i:i+3])
        minhash.update(shingle.encode("utf-8"))
    return minhash


def _deduplicate_jaccard_fallback(articles: list) -> list:
    """
    Fallback sin datasketch: deduplicación simple por Jaccard de n-grams.
    O(n²) — solo para listas pequeñas (<500 artículos).
    """
    def jaccard_similarity(a1, a2):
        tokens1 = set(a1.title.lower().split())
        tokens2 = set(a2.title.lower().split())
        if not tokens1 or not tokens2:
            return 0.0
        return len(tokens1 & tokens2) / len(tokens1 | tokens2)

    kept = []
    for i, article in enumerate(articles):
        is_dup = False
        for kept_article in kept:
            if jaccard_similarity(article, kept_article) > 0.7:
                is_dup = True
                break
        if not is_dup:
            kept.append(article)

    logger.info(f"Near-dedup Jaccard fallback: {len(articles)} → {len(kept)} artículos")
    return kept


# ─────────────────────────────────────────────────────────────────────────────
# PASO 2: EMBEDDING Y CLUSTERING (sentence-transformers + DBSCAN)
# ─────────────────────────────────────────────────────────────────────────────

_embedding_model = None

def _get_embedding_model():
    """Lazy loading del modelo de embeddings."""
    global _embedding_model
    if _embedding_model is None:
        logger.info(f"Cargando modelo de embeddings: {EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Modelo cargado correctamente")
    return _embedding_model


def compute_embeddings(articles: list) -> np.ndarray:
    """
    Genera embeddings multilingüe para todos los artículos.
    Usa título + resumen como input para cada artículo.
    """
    if not HAS_SENTENCE_TRANSFORMERS:
        return _compute_tfidf_embeddings(articles)

    model = _get_embedding_model()
    texts = [f"{a.title}. {a.summary[:300]}" for a in articles]

    logger.info(f"Generando embeddings para {len(texts)} artículos...")
    embeddings = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=False,
        normalize_embeddings=True,  # Normalizar para que cosine sim = dot product
    )

    # Asignar embedding a cada artículo
    for article, emb in zip(articles, embeddings):
        article.embedding = emb

    return embeddings


def _compute_tfidf_embeddings(articles: list) -> np.ndarray:
    """Fallback con TF-IDF si sentence-transformers no está disponible."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    texts = [f"{a.title} {a.summary[:300]}" for a in articles]
    vectorizer = TfidfVectorizer(max_features=5000, stop_words=None)
    raw = vectorizer.fit_transform(texts).toarray()

    # Normalizar a vectores unitarios para que cosine_distance = 1 - dot_product
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    norms[norms == 0] = 1
    embeddings = raw / norms

    for article, emb in zip(articles, embeddings):
        article.embedding = emb

    logger.info("Embeddings TF-IDF normalizados generados (modo fallback)")
    return embeddings


def cluster_articles(articles: list, embeddings: np.ndarray) -> list[EventCluster]:
    """
    Agrupa artículos en clusters por evento usando DBSCAN con distancia coseno.

    DBSCAN es ideal porque:
    - No requiere K predefinido (no sabemos cuántos eventos hay)
    - Marca como "ruido" artículos que no pertenecen a ningún cluster
    - Maneja clusters de formas arbitrarias
    """
    if not HAS_SKLEARN:
        return _cluster_simple_fallback(articles)

    # Calcular distancia coseno (DBSCAN trabaja con distancias, no similitudes)
    # embeddings ya están normalizados, por lo que cosine_distance = 1 - dot_product
    distance_matrix = 1 - np.dot(embeddings, embeddings.T)
    distance_matrix = np.clip(distance_matrix, 0, None)  # Evitar valores negativos por float precision

    # Seleccionar eps según el modo de embedding real (no heurística de distancia)
    dist_mean = distance_matrix[distance_matrix > 0].mean()
    if HAS_SENTENCE_TRANSFORMERS and _embedding_model is not None:
        # sentence-transformers cargado: eps calibrado para similitud semántica real
        # 0.35 = cosine distance → similarity > 0.65 (mismo evento, distintas fuentes)
        eps = DBSCAN_EPS
        logger.info(f"Modo sentence-transformers (dist_mean={dist_mean:.3f}) → eps: {eps:.3f}")
    else:
        # TF-IDF: vectores sparse, distancias más altas → eps adaptativo
        eps = max(0.65, dist_mean * 0.72)
        logger.info(f"Modo TF-IDF (dist_mean={dist_mean:.3f}) → eps adaptado: {eps:.3f}")

    logger.info(f"Ejecutando DBSCAN sobre {len(articles)} artículos...")
    db = DBSCAN(
        eps=eps,
        min_samples=DBSCAN_MIN_SAMPLES,
        metric="precomputed",
        algorithm="auto",
        n_jobs=-1,  # Usar todos los cores
    )
    labels = db.fit_predict(distance_matrix)

    # Construir clusters
    clusters = _build_clusters(articles, labels, embeddings)
    logger.info(f"Clustering completo: {len(clusters)} eventos identificados")

    return clusters


def _build_clusters(articles: list, labels: np.ndarray, embeddings: np.ndarray) -> list[EventCluster]:
    """Construye objetos EventCluster a partir de los labels DBSCAN."""
    from collections import defaultdict

    # Agrupar artículos por label
    label_groups: dict[int, list] = defaultdict(list)
    for article, label in zip(articles, labels):
        label_groups[label].append(article)

    clusters = []
    cluster_idx = 0

    for label, group_articles in sorted(label_groups.items()):
        cluster = EventCluster()
        cluster.cluster_id = f"evt_{datetime.now().strftime('%Y%m%d')}_{cluster_idx:03d}"
        cluster.is_noise = (label == -1)

        # Cap de tamaño para evitar mega-clusters (pueden indicar sobre-agrupación)
        if len(group_articles) > MAX_CLUSTER_SIZE:
            group_articles = group_articles[:MAX_CLUSTER_SIZE]

        cluster.articles = group_articles
        cluster.article_ids = [a.id for a in group_articles]
        cluster.article_count = len(group_articles)

        # Diversidad de fuentes
        cluster.unique_sources = len(set(a.source_name for a in group_articles))
        cluster.regions = list(set(a.source_region for a in group_articles))
        cluster.unique_regions = len(cluster.regions)

        # Fecha del evento: primera publicación
        dates = [a.published_at for a in group_articles if a.published_at]
        cluster.first_seen = min(dates) if dates else datetime.now(timezone.utc)

        # Artículo representativo: el más completo de la fuente de mayor tier
        cluster.representative_article = _select_representative(group_articles)

        # Label del evento: título del artículo representativo
        if cluster.representative_article:
            cluster.event_label = cluster.representative_article.title

        # Centroide del embedding del cluster
        group_indices = [i for i, a in enumerate(articles) if a.id in set(cluster.article_ids)]
        if group_indices:
            cluster.centroid_embedding = embeddings[group_indices].mean(axis=0)

        clusters.append(cluster)
        cluster_idx += 1

    # Ordenar por número de artículos (señal de importancia, aunque no la única)
    clusters.sort(key=lambda c: c.article_count, reverse=True)
    return clusters


def _select_representative(articles: list) -> object:
    """
    Elige el artículo más representativo del cluster.
    Criterio: tier 1, texto más largo, bias más bajo.
    """
    return sorted(
        articles,
        key=lambda a: (
            a.source_tier,           # Tier 1 primero
            a.source_bias,           # Menos bias primero
            -a.word_count,           # Más palabras primero
        )
    )[0]


def _cluster_simple_fallback(articles: list) -> list[EventCluster]:
    """Fallback sin sklearn: cada artículo es su propio cluster."""
    logger.warning("Clustering simple fallback (sin DBSCAN): cada artículo = 1 evento")
    clusters = []
    for i, article in enumerate(articles):
        c = EventCluster()
        c.cluster_id = f"evt_{datetime.now().strftime('%Y%m%d')}_{i:03d}"
        c.articles = [article]
        c.article_ids = [article.id]
        c.article_count = 1
        c.unique_sources = 1
        c.regions = [article.source_region]
        c.unique_regions = 1
        c.representative_article = article
        c.event_label = article.title
        c.first_seen = article.published_at or datetime.now(timezone.utc)
        clusters.append(c)
    return clusters


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE COMPLETO DE CLUSTERING
# ─────────────────────────────────────────────────────────────────────────────

def run_clustering_pipeline(articles: list) -> list[EventCluster]:
    """
    Pipeline completo:
    1. Deduplicación near-duplicate (MinHash)
    2. Embeddings multilingüe
    3. DBSCAN clustering
    4. Retorna lista de EventClusters ordenados
    """
    logger.info(f"Pipeline de clustering iniciado con {len(articles)} artículos")

    # Paso 1: dedup near-duplicate
    articles = deduplicate_minhash(articles)

    # Paso 2: embeddings
    embeddings = compute_embeddings(articles)

    # Paso 3: clustering
    clusters = cluster_articles(articles, embeddings)

    # Estadísticas
    noise_count = sum(1 for c in clusters if c.is_noise)
    real_clusters = [c for c in clusters if not c.is_noise]

    logger.info(
        f"Clustering completo: {len(real_clusters)} eventos reales + {noise_count} artículos ruido"
    )

    return clusters


def print_cluster_stats(clusters: list[EventCluster]):
    """Imprime estadísticas de los clusters identificados."""
    real = [c for c in clusters if not c.is_noise]
    noise = [c for c in clusters if c.is_noise]

    print(f"\n{'='*70}")
    print(f"EVENTOS IDENTIFICADOS: {len(real)} clusters + {len(noise)} artículos ruido")
    print(f"{'='*70}")

    for i, cluster in enumerate(real[:20]):  # Top 20
        print(f"\n[{i+1:02d}] {cluster.event_label[:70]}")
        print(f"     Artículos: {cluster.article_count} | "
              f"Fuentes: {cluster.unique_sources} | "
              f"Regiones: {cluster.unique_regions} ({', '.join(cluster.regions[:3])})")

    print(f"{'='*70}\n")
