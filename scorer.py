"""
scorer.py — Motor de scoring editorial multidimensional.

Este es el corazón del sistema. Evalúa cada cluster/evento en 7 dimensiones
de importancia global REAL, sin ninguna señal de popularidad o viralidad.

Las señales usadas son:
- Texto del artículo (keywords, entidades geopolíticas)
- Metadata de las fuentes (tier, diversidad regional)
- Metadata del cluster (cantidad y diversidad de fuentes)
- Señales GDELT (si disponible) como ground truth de magnitud del evento
- Claude API como evaluador editorial de alto nivel (opcional)

Score final: 0-100 puntos
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# PESOS DEL SCORING (deben sumar 1.0)
# ─────────────────────────────────────────────────────────────────────────────

DIMENSION_WEIGHTS = {
    "geopolitical_impact":  0.25,   # Guerras, tratados, cambios de régimen
    "economic_impact":      0.20,   # Crisis financieras, mercados, sanciones
    "geographic_reach":     0.15,   # Cuántos países/regiones afecta
    "severity_urgency":     0.15,   # Muertes, desastres, decisiones irreversibles
    "source_diversity":     0.10,   # Diversidad de outlets y regiones
    "topic_persistence":    0.10,   # Evento nuevo vs. crisis en curso
    "institutional_rel":    0.05,   # Involucra ONU, G7, OTAN, OMS, etc.
}

assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 0.001, "Los pesos deben sumar 1.0"

# ─────────────────────────────────────────────────────────────────────────────
# KEYWORDS POR DIMENSIÓN
# ─────────────────────────────────────────────────────────────────────────────

GEOPOLITICAL_KEYWORDS = {
    "high": [
        "war", "invasion", "military", "troops", "coup", "regime", "sanctions",
        "nuclear", "missile", "ceasefire", "treaty", "diplomacy", "expelled",
        "guerra", "invasión", "tropas", "golpe", "sanciones", "misil",
        "conflict", "offensive", "aggression", "declaration", "escalation",
        "embargo", "sovereignty", "occupation", "annexation",
    ],
    "medium": [
        "election", "summit", "agreement", "bilateral", "protest", "uprising",
        "referendum", "opposition", "parliament", "crisis", "tension",
        "elección", "cumbre", "acuerdo", "bilateral", "protesta",
        "government", "minister", "president", "foreign policy",
    ],
    "low": [
        "meeting", "visit", "statement", "call", "talks", "discuss",
        "reunión", "visita", "declaración",
    ],
}

ECONOMIC_KEYWORDS = {
    "high": [
        "recession", "crash", "collapse", "default", "bankruptcy", "inflation",
        "hyperinflation", "crisis", "bailout", "IMF", "debt", "currency",
        "devaluation", "financial crisis", "bank run", "market crash",
        "recesión", "colapso", "quiebra", "inflación", "deuda", "moneda",
        "tariff", "trade war", "sanctions", "supply chain", "oil price",
        "interest rate", "federal reserve", "central bank",
    ],
    "medium": [
        "GDP", "growth", "unemployment", "trade", "investment", "stock",
        "market", "economy", "fiscal", "budget", "deficit", "surplus",
        "PIB", "crecimiento", "desempleo", "comercio", "inversión",
        "commodities", "oil", "gas", "energy", "exports", "imports",
    ],
    "low": [
        "profit", "earnings", "revenue", "company", "deal", "merger",
        "acquisition",
    ],
}

SEVERITY_KEYWORDS = {
    "critical": [
        "dead", "killed", "deaths", "casualties", "genocide", "massacre",
        "famine", "starvation", "earthquake", "tsunami", "nuclear",
        "muertos", "víctimas", "masacre", "hambruna", "terremoto",
        "pandemic", "outbreak", "epidemic", "explosion", "attack",
        "atentado", "explosión", "brote", "emergencia nacional",
        "humanitarian crisis", "displacement", "refugees",
        "civilian", "war crimes", "chemical weapons",
    ],
    "high": [
        "injury", "wounded", "arrested", "detained", "collapsed",
        "emergency", "evacuation", "fire", "flood", "drought",
        "injured", "heridos", "detenidos", "evacuación",
        "protest", "riot", "violence", "conflict",
    ],
    "medium": [
        "warning", "alert", "risk", "threat", "concern",
        "advertencia", "alerta", "riesgo", "amenaza",
    ],
}

INSTITUTIONAL_KEYWORDS = [
    "united nations", "UN", "security council", "NATO", "G7", "G20",
    "IMF", "World Bank", "WHO", "WTO", "IAEA", "OPEC", "EU", "European Union",
    "African Union", "Arab League", "ASEAN", "OAS", "ICC",
    "naciones unidas", "consejo de seguridad", "OTAN", "FMI",
    "secretary general", "resolution", "resolution 2024", "emergency session",
    "general assembly",
]

TOPIC_PERSISTENCE_KEYWORDS = [
    "ongoing", "continues", "escalates", "still", "day", "week", "month",
    "crisis", "war", "conflict", "standoff", "impasse", "negotiations",
    "continúa", "sigue", "escala", "día", "semana", "crisis",
]

# ─────────────────────────────────────────────────────────────────────────────
# BOOSTS CONTEXTUALES
# ─────────────────────────────────────────────────────────────────────────────

CONTEXTUAL_BOOSTS = {
    "nuclear_risk": {
        "keywords": ["nuclear", "warhead", "missile", "launch", "ICBM", "radiation"],
        "boost": 20,
        "reason": "Riesgo nuclear — máxima prioridad",
    },
    "pandemic_outbreak": {
        "keywords": ["pandemic", "outbreak", "novel virus", "WHO declares", "new strain"],
        "boost": 18,
        "reason": "Brote pandémico declarado por OMS",
    },
    "armed_conflict_active": {
        "keywords": ["war", "invasion", "troops advance", "offensive", "casualties reported"],
        "boost": 15,
        "reason": "Conflicto armado activo o en escalada",
    },
    "financial_systemic_crisis": {
        "keywords": ["bank run", "financial collapse", "sovereign default", "market crash"],
        "boost": 12,
        "reason": "Crisis financiera sistémica",
    },
    "regime_change": {
        "keywords": ["coup", "overthrow", "government collapsed", "president fled"],
        "boost": 10,
        "reason": "Cambio de régimen o golpe de estado",
    },
    "un_security_council_emergency": {
        "keywords": ["security council emergency", "emergency session", "veto"],
        "boost": 8,
        "reason": "Sesión de emergencia del Consejo de Seguridad ONU",
    },
    "major_natural_disaster": {
        "keywords": ["earthquake", "tsunami", "hurricane", "magnitude 7", "millions affected"],
        "boost": 8,
        "reason": "Desastre natural de gran escala",
    },
    "multilateral_sanctions": {
        "keywords": ["sanctions", "embargo", "G7 sanctions", "EU sanctions", "US sanctions"],
        "boost": 7,
        "reason": "Sanciones económicas multilaterales",
    },
}

# Penalización para temas de entretenimiento/virales
ENTERTAINMENT_PENALTIES = [
    "celebrity", "oscar", "grammy", "entertainment", "actor", "singer",
    "sports", "football", "basketball", "tennis", "game", "movie",
    "trending", "viral", "influencer", "social media", "tiktok",
    "famoso", "música", "cine", "deporte", "fútbol", "baloncesto",
]


# ─────────────────────────────────────────────────────────────────────────────
# MODELO DE SCORE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScoreBreakdown:
    geopolitical_impact: float = 0.0
    economic_impact: float = 0.0
    geographic_reach: float = 0.0
    severity_urgency: float = 0.0
    source_diversity: float = 0.0
    topic_persistence: float = 0.0
    institutional_rel: float = 0.0
    boosts_applied: list = field(default_factory=list)
    boost_total: float = 0.0
    regional_penalty: float = 0.0
    entertainment_penalty: float = 0.0
    total_score: float = 0.0
    rank: int = 0
    why_top5: str = ""
    why_excluded: str = ""
    macrotema: str = ""       # clasificado por get_top_n_diverse
    broad_region: str = ""    # región amplia clasificada por get_top_n_diverse

    def to_dict(self) -> dict:
        return {
            "geopolitical_impact":  {"raw": round(self.geopolitical_impact, 2), "weight": DIMENSION_WEIGHTS["geopolitical_impact"], "contribution": round(self.geopolitical_impact * DIMENSION_WEIGHTS["geopolitical_impact"] * 10, 2)},
            "economic_impact":      {"raw": round(self.economic_impact, 2),     "weight": DIMENSION_WEIGHTS["economic_impact"],     "contribution": round(self.economic_impact * DIMENSION_WEIGHTS["economic_impact"] * 10, 2)},
            "geographic_reach":     {"raw": round(self.geographic_reach, 2),    "weight": DIMENSION_WEIGHTS["geographic_reach"],    "contribution": round(self.geographic_reach * DIMENSION_WEIGHTS["geographic_reach"] * 10, 2)},
            "severity_urgency":     {"raw": round(self.severity_urgency, 2),    "weight": DIMENSION_WEIGHTS["severity_urgency"],    "contribution": round(self.severity_urgency * DIMENSION_WEIGHTS["severity_urgency"] * 10, 2)},
            "source_diversity":     {"raw": round(self.source_diversity, 2),    "weight": DIMENSION_WEIGHTS["source_diversity"],    "contribution": round(self.source_diversity * DIMENSION_WEIGHTS["source_diversity"] * 10, 2)},
            "topic_persistence":    {"raw": round(self.topic_persistence, 2),   "weight": DIMENSION_WEIGHTS["topic_persistence"],   "contribution": round(self.topic_persistence * DIMENSION_WEIGHTS["topic_persistence"] * 10, 2)},
            "institutional_rel":    {"raw": round(self.institutional_rel, 2),   "weight": DIMENSION_WEIGHTS["institutional_rel"],   "contribution": round(self.institutional_rel * DIMENSION_WEIGHTS["institutional_rel"] * 10, 2)},
            "boosts_applied": self.boosts_applied,
            "boost_total": round(self.boost_total, 2),
            "regional_penalty": round(self.regional_penalty, 2),
            "entertainment_penalty": round(self.entertainment_penalty, 2),
            "total_score": round(self.total_score, 2),
        }


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES DE SCORING POR DIMENSIÓN
# ─────────────────────────────────────────────────────────────────────────────

def _keyword_score(text: str, keyword_dict: dict, normalize: float = 10.0) -> float:
    """
    Puntúa un texto según keywords por nivel.
    Retorna valor en escala 0-10.
    """
    text_lower = text.lower()
    score = 0.0

    high_matches = sum(1 for kw in keyword_dict.get("high", []) if kw.lower() in text_lower)
    med_matches = sum(1 for kw in keyword_dict.get("medium", []) if kw.lower() in text_lower)
    low_matches = sum(1 for kw in keyword_dict.get("low", []) if kw.lower() in text_lower)

    score = (high_matches * 3.0) + (med_matches * 1.5) + (low_matches * 0.5)
    return min(score, normalize)


def score_geopolitical_impact(cluster) -> float:
    """Score 0-10: impacto geopolítico del evento."""
    text = _get_cluster_text(cluster)
    raw = _keyword_score(text, GEOPOLITICAL_KEYWORDS)

    # Boost si involucra países con poder nuclear o P5 del CS ONU
    major_powers = ["united states", "china", "russia", "france", "united kingdom",
                    "india", "pakistan", "israel", "north korea", "iran"]
    power_count = sum(1 for p in major_powers if p in text.lower())
    if power_count >= 2:
        raw = min(raw + 2.0, 10.0)
    elif power_count == 1:
        raw = min(raw + 1.0, 10.0)

    return min(raw, 10.0)


def score_economic_impact(cluster) -> float:
    """Score 0-10: impacto económico global."""
    text = _get_cluster_text(cluster)
    return min(_keyword_score(text, ECONOMIC_KEYWORDS), 10.0)


def score_geographic_reach(cluster) -> float:
    """
    Score 0-10: alcance geográfico del evento.
    Basado en: regiones del cluster + menciones de países en el texto.
    """
    regions = cluster.unique_regions
    sources = cluster.unique_sources

    # Base: regiones cubiertas por las fuentes
    region_score = min(regions * 2.0, 8.0)

    # Bonus: diversidad de fuentes
    source_bonus = min(sources * 0.3, 2.0)

    return min(region_score + source_bonus, 10.0)


def score_severity(cluster) -> float:
    """Score 0-10: severidad y urgencia del evento."""
    text = _get_cluster_text(cluster)
    text_lower = text.lower()

    score = 0.0
    critical_matches = sum(1 for kw in SEVERITY_KEYWORDS["critical"] if kw.lower() in text_lower)
    high_matches = sum(1 for kw in SEVERITY_KEYWORDS["high"] if kw.lower() in text_lower)
    med_matches = sum(1 for kw in SEVERITY_KEYWORDS["medium"] if kw.lower() in text_lower)

    score = (critical_matches * 4.0) + (high_matches * 2.0) + (med_matches * 0.5)
    return min(score, 10.0)


def score_source_diversity(cluster) -> float:
    """
    Score 0-10: diversidad y credibilidad de las fuentes.
    Penaliza si una sola región domina >60% del cluster.
    """
    from collections import Counter

    if cluster.article_count == 0:
        return 0.0

    unique_sources = cluster.unique_sources
    unique_regions = cluster.unique_regions
    total_articles = cluster.article_count

    # Base: diversidad de fuentes (5 sources = 5 puntos, máx 8)
    source_score = min(unique_sources * 0.8, 8.0)

    # Bonus: diversidad regional (cada región extra suma)
    region_bonus = min(unique_regions * 0.5, 2.0)

    base_score = source_score + region_bonus

    # Penalización si una región domina
    region_counts = Counter(a.source_region for a in cluster.articles)
    if region_counts:
        dominant_region_ratio = max(region_counts.values()) / total_articles
        if dominant_region_ratio > 0.6:
            base_score *= 0.75
        elif dominant_region_ratio > 0.8:
            base_score *= 0.5

    # Penalización por fuentes de baja calidad (tier 3 dominante)
    tier3_ratio = sum(1 for a in cluster.articles if a.source_tier == 3) / total_articles
    if tier3_ratio > 0.5:
        base_score *= 0.8

    return min(base_score, 10.0)


def score_persistence(cluster) -> float:
    """
    Score 0-10: persistencia del tema.
    Distingue entre noticia de un día y crisis en curso.
    """
    text = _get_cluster_text(cluster)
    text_lower = text.lower()

    # Señales de evento en curso
    persistence_matches = sum(1 for kw in TOPIC_PERSISTENCE_KEYWORDS if kw.lower() in text_lower)
    days_active = cluster.days_active

    base = min(persistence_matches * 1.5, 7.0)
    days_bonus = min(days_active * 0.5, 3.0)

    return min(base + days_bonus, 10.0)


def score_institutional(cluster) -> float:
    """Score 0-10: relevancia institucional (ONU, G7, OTAN, OMS, etc.)."""
    text = _get_cluster_text(cluster).lower()
    matches = sum(1 for kw in INSTITUTIONAL_KEYWORDS if kw.lower() in text)
    return min(matches * 2.5, 10.0)


# ─────────────────────────────────────────────────────────────────────────────
# BOOSTS Y PENALIZACIONES
# ─────────────────────────────────────────────────────────────────────────────

def apply_contextual_boosts(cluster, base_score: float, breakdown: ScoreBreakdown) -> float:
    """Aplica boosts por contexto crítico (nuclear, pandemia, golpe, etc.)."""
    text = _get_cluster_text(cluster).lower()
    total_boost = 0.0

    for boost_name, boost_config in CONTEXTUAL_BOOSTS.items():
        keywords = boost_config["keywords"]
        matches = sum(1 for kw in keywords if kw.lower() in text)
        if matches >= 2:  # Necesita al menos 2 keywords para activar el boost
            boost_value = boost_config["boost"]
            total_boost += boost_value
            breakdown.boosts_applied.append(f"{boost_name} (+{boost_value})")
            logger.debug(f"Boost activado: {boost_name} para '{cluster.event_label[:50]}'")

    breakdown.boost_total = total_boost
    return min(base_score + total_boost, 100.0)


def apply_entertainment_penalty(cluster, score: float, breakdown: ScoreBreakdown) -> float:
    """Penaliza eventos de entretenimiento/viralidad."""
    text = _get_cluster_text(cluster).lower()
    penalty_matches = sum(1 for kw in ENTERTAINMENT_PENALTIES if kw in text)

    if penalty_matches >= 3:
        penalty = min(penalty_matches * 5.0, 50.0)
        breakdown.entertainment_penalty = penalty
        return max(score - penalty, 0.0)

    return score


def apply_regional_penalty(cluster, score: float, breakdown: ScoreBreakdown) -> float:
    """Penaliza eventos con cobertura de una sola región."""
    if cluster.unique_regions == 1:
        breakdown.regional_penalty = 15.0
        return max(score - 15.0, 0.0)
    elif cluster.unique_regions == 2 and cluster.unique_sources < 5:
        breakdown.regional_penalty = 5.0
        return max(score - 5.0, 0.0)

    return score


# ─────────────────────────────────────────────────────────────────────────────
# FILTROS DE EXCLUSIÓN FORZADA
# ─────────────────────────────────────────────────────────────────────────────

def is_excluded(cluster) -> tuple[bool, str]:
    """
    Verifica si el evento debe ser excluido del ranking.
    Retorna (excluido: bool, razón: str)
    """
    text = _get_cluster_text(cluster).lower()
    title = cluster.event_label.lower()

    # Menos de 2 fuentes independientes
    if cluster.unique_sources < 2:
        return True, f"Solo {cluster.unique_sources} fuente(s) independiente(s) — mínimo 2"

    # Detección de entretenimiento puro
    entertainment_count = sum(1 for kw in ENTERTAINMENT_PENALTIES if kw in text)
    if entertainment_count >= 4:
        return True, "Contenido de entretenimiento sin relevancia geopolítica"

    # Solo un país mencionado Y ninguna señal geopolítica
    geopolit_count = sum(1 for kw in GEOPOLITICAL_KEYWORDS["high"] if kw in text)
    econ_count = sum(1 for kw in ECONOMIC_KEYWORDS["high"] if kw in text)
    if geopolit_count == 0 and econ_count == 0 and cluster.unique_regions <= 1:
        return True, "Sin señales geopolíticas ni económicas de relevancia internacional"

    return False, ""


# ─────────────────────────────────────────────────────────────────────────────
# GENERACIÓN DE EXPLICACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def generate_explanation(cluster, breakdown: ScoreBreakdown) -> str:
    """Genera una explicación en lenguaje natural de por qué el evento entró al top 5."""
    parts = []

    # Fuentes
    parts.append(f"Cubierto por {cluster.unique_sources} medios independientes en {cluster.unique_regions} región(es)")

    # Dimensión dominante
    scores = {
        "impacto geopolítico": breakdown.geopolitical_impact,
        "impacto económico": breakdown.economic_impact,
        "alcance geográfico": breakdown.geographic_reach,
        "severidad": breakdown.severity_urgency,
    }
    top_dim = max(scores, key=scores.get)
    top_val = scores[top_dim]
    if top_val > 6:
        parts.append(f"Alto {top_dim} ({top_val:.1f}/10)")

    # Boosts aplicados
    if breakdown.boosts_applied:
        boost_names = [b.split(" (+")[0].replace("_", " ") for b in breakdown.boosts_applied]
        parts.append(f"Boost contextual: {', '.join(boost_names)}")

    # Persistencia
    if cluster.days_active > 1:
        parts.append(f"Evento en curso hace {cluster.days_active} día(s)")

    return ". ".join(parts) + "."


# ─────────────────────────────────────────────────────────────────────────────
# SCORER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def score_cluster(cluster) -> ScoreBreakdown:
    """
    Calcula el score completo para un cluster/evento.
    Retorna un objeto ScoreBreakdown con el desglose por dimensión.
    """
    breakdown = ScoreBreakdown()

    # Verificar exclusión
    excluded, reason = is_excluded(cluster)
    if excluded:
        breakdown.total_score = 0.0
        breakdown.why_excluded = reason
        return breakdown

    # Calcular dimensiones (escala 0-10 cada una)
    breakdown.geopolitical_impact = score_geopolitical_impact(cluster)
    breakdown.economic_impact = score_economic_impact(cluster)
    breakdown.geographic_reach = score_geographic_reach(cluster)
    breakdown.severity_urgency = score_severity(cluster)
    breakdown.source_diversity = score_source_diversity(cluster)
    breakdown.topic_persistence = score_persistence(cluster)
    breakdown.institutional_rel = score_institutional(cluster)

    # Score base ponderado (escala 0-100)
    base_score = (
        breakdown.geopolitical_impact * DIMENSION_WEIGHTS["geopolitical_impact"] * 10 +
        breakdown.economic_impact     * DIMENSION_WEIGHTS["economic_impact"]     * 10 +
        breakdown.geographic_reach    * DIMENSION_WEIGHTS["geographic_reach"]    * 10 +
        breakdown.severity_urgency    * DIMENSION_WEIGHTS["severity_urgency"]    * 10 +
        breakdown.source_diversity    * DIMENSION_WEIGHTS["source_diversity"]    * 10 +
        breakdown.topic_persistence   * DIMENSION_WEIGHTS["topic_persistence"]   * 10 +
        breakdown.institutional_rel   * DIMENSION_WEIGHTS["institutional_rel"]   * 10
    )

    # Aplicar boosts
    score = apply_contextual_boosts(cluster, base_score, breakdown)

    # Aplicar penalizaciones
    score = apply_entertainment_penalty(cluster, score, breakdown)
    score = apply_regional_penalty(cluster, score, breakdown)

    breakdown.total_score = round(min(max(score, 0.0), 100.0), 2)
    breakdown.why_top5 = generate_explanation(cluster, breakdown)

    return breakdown


def rank_clusters(clusters: list) -> list[tuple]:
    """
    Rankea todos los clusters y retorna lista de (cluster, breakdown) ordenada por score.
    Excluye clusters de ruido (sin agrupación) salvo que sean muy importantes.
    """
    scored = []

    for cluster in clusters:
        if cluster.is_noise and cluster.unique_sources < 2:
            continue  # Ignorar ruido con poca cobertura

        breakdown = score_cluster(cluster)

        if breakdown.total_score > 0:
            scored.append((cluster, breakdown))

    # Ordenar por score descendente
    scored.sort(key=lambda x: x[1].total_score, reverse=True)

    # Asignar ranks
    for i, (cluster, breakdown) in enumerate(scored):
        breakdown.rank = i + 1

    return scored


def get_top_n(clusters: list, n: int = 5) -> list[tuple]:
    """Retorna los N clusters más importantes con su breakdown."""
    selected, _ = get_top_n_diverse(clusters, n=n)
    return selected


# ─────────────────────────────────────────────────────────────────────────────
# CLASIFICACIÓN POR MACROTEMA
# ─────────────────────────────────────────────────────────────────────────────

MACROTEMA_KEYWORDS = {
    "geopolítica/guerra": [
        "war", "conflict", "military", "attack", "troops", "nato", "missile",
        "strike", "iran", "ukraine", "russia", "israel", "houthi", "terror",
        "nuclear", "sanction", "weapon", "army", "bomb", "fighter", "combat",
        "airstrike", "offensive", "ceasefire", "troops", "pentagon", "warship",
        "guerra", "conflicto", "ataque", "misil", "bombardeo", "tropas",
        "killed", "wounded", "casualties", "muertos", "heridos"
    ],
    "economía/mercados": [
        "economy", "market", "trade", "tariff", "gdp", "recession", "inflation",
        "bank", "oil", "energy", "price", "dollar", "euro", "fed", "imf",
        "supply chain", "export", "import", "deficit", "debt", "interest rate",
        "stock", "bond", "crypto", "bitcoin", "growth", "unemployment",
        "economía", "mercado", "comercio", "aranceles", "petróleo", "energía",
        "reserva federal", "banco central", "crecimiento"
    ],
    "política/institucional": [
        "election", "president", "government", "minister", "congress", "parliament",
        "vote", "political", "party", "protest", "coup", "democracy", "reform",
        "arrested", "impeachment", "corruption", "court", "judge", "law",
        "constitution", "prime minister", "chancellor", "senate",
        "elección", "gobierno", "presidente", "ministro", "protesta", "golpe",
        "democracia", "corrupción", "tribunal", "juicio", "ley"
    ],
    "tecnología/IA": [
        "artificial intelligence", "ai ", " ai,", "tech", "cyber", "hack",
        "data breach", "digital", "chip", "semiconductor", "robot", "quantum",
        "space", "satellite", "launch", "software", "algorithm", "deepfake",
        "surveillance", "privacy", "elon musk", "openai", "google", "microsoft",
        "tecnología", "inteligencia artificial", "ciberseguridad", "datos",
        "desinformación"
    ],
    "clima/salud/sociedad": [
        "climate", "flood", "earthquake", "hurricane", "wildfire", "tsunami",
        "disaster", "health", "pandemic", "disease", "virus", "outbreak",
        "humanitarian", "refugee", "hunger", "famine", "food", "water",
        "cop", "migration", "immigration", "demographic",
        "clima", "inundación", "terremoto", "desastre", "salud", "pandemia",
        "enfermedad", "humanitario", "refugiados", "hambre", "sequía"
    ],
}


def classify_macrotema(cluster) -> str:
    """
    Clasifica un cluster en uno de 5 macrotemas basado en keywords del label
    y del artículo representativo. Retorna el macrotema dominante.
    """
    text = cluster.event_label.lower()
    if cluster.representative_article:
        rep = cluster.representative_article
        text += " " + (rep.title or "").lower()
        text += " " + (rep.summary or "").lower()

    scores = {tema: 0 for tema in MACROTEMA_KEYWORDS}
    for tema, keywords in MACROTEMA_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                scores[tema] += 1

    best = max(scores, key=scores.get)
    # Si no matchea nada claro, usar geopolítica como default (suele ser el más frecuente)
    return best if scores[best] > 0 else "geopolítica/guerra"


def classify_region_broad(cluster) -> str:
    """Agrupa las regiones del cluster en una zona geográfica amplia."""
    regions = set(cluster.regions) if cluster.regions else set()
    region_map = {
        "global": "global",
        "americas": "américas",
        "europe_west": "europa",
        "europe_east": "europa",
        "middle_east_north_africa": "medio_oriente/africa_norte",
        "asia_pacific": "asia/pacífico",
        "africa_sub_saharan": "africa_subsahariana",
        "specialized": "global",
    }
    broad = set()
    for r in regions:
        broad.add(region_map.get(r, "otros"))
    if len(broad) > 2:
        return "global"
    return list(broad)[0] if broad else "global"


def get_top_n_diverse(clusters: list, n: int = 5) -> tuple[list, list]:
    """
    Selecciona el Top N con diversidad obligatoria:
    - Máx 2 por macrotema
    - Máx 2 por región amplia
    Retorna (seleccionados, excluidos_por_diversidad).
    """
    ranked = rank_clusters(clusters)

    selected = []
    excluded_diversity = []  # Excluidos solo por regla de diversidad
    macrotema_count: dict[str, int] = {}
    region_count: dict[str, int] = {}

    MAX_PER_MACROTEMA = 2
    MAX_PER_REGION = 2

    for cluster, breakdown in ranked:
        if len(selected) >= n:
            break

        tema = classify_macrotema(cluster)
        region = classify_region_broad(cluster)

        # Guardar en breakdown para uso posterior en formatter
        breakdown.macrotema = tema
        breakdown.broad_region = region

        if (macrotema_count.get(tema, 0) >= MAX_PER_MACROTEMA or
                region_count.get(region, 0) >= MAX_PER_REGION):
            excluded_diversity.append((cluster, breakdown, "diversidad"))
            continue

        selected.append((cluster, breakdown))
        macrotema_count[tema] = macrotema_count.get(tema, 0) + 1
        region_count[region] = region_count.get(region, 0) + 1

    # Si con las restricciones no llenamos n, relajamos y completamos
    if len(selected) < n:
        for cluster, breakdown in ranked:
            if len(selected) >= n:
                break
            if (cluster, breakdown) not in selected:
                tema = classify_macrotema(cluster)
                region = classify_region_broad(cluster)
                breakdown.macrotema = tema
                breakdown.broad_region = region
                selected.append((cluster, breakdown))

    # Los restantes del ranking que no entraron (top candidatos que quedaron fuera)
    selected_clusters = {id(c) for c, _ in selected}
    not_selected = [
        (c, bd) for c, bd in ranked
        if id(c) not in selected_clusters
    ]

    return selected, not_selected


def rank_all_including_noise(clusters: list, noise_articles: list) -> list[tuple]:
    """
    Rankea clusters reales + artículos individuales (ruido DBSCAN).
    Útil cuando hay pocas fuentes y muchos artículos quedan sin cluster.
    """
    scored = []

    # Rankear clusters reales primero
    for cluster in clusters:
        if not cluster.is_noise:
            breakdown = score_cluster(cluster)
            if breakdown.total_score > 0:
                scored.append((cluster, breakdown))

    # Si tenemos menos de N resultados, incluir artículos individuales
    if len(scored) < 5 and noise_articles:
        for article in noise_articles:
            # Crear cluster sintético de 1 artículo
            from clusterer import EventCluster
            from datetime import datetime, timezone
            c = EventCluster()
            c.cluster_id = f"single_{article.id}"
            c.articles = [article]
            c.article_ids = [article.id]
            c.article_count = 1
            c.unique_sources = 1
            c.regions = [article.source_region]
            c.unique_regions = 1
            c.representative_article = article
            c.event_label = article.title
            c.first_seen = article.published_at or datetime.now(timezone.utc)
            c.is_noise = True

            breakdown = score_cluster(c)
            if breakdown.total_score > 5:  # Umbral mínimo
                scored.append((c, breakdown))

    scored.sort(key=lambda x: x[1].total_score, reverse=True)
    for i, (c, b) in enumerate(scored):
        b.rank = i + 1

    return scored


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDAD
# ─────────────────────────────────────────────────────────────────────────────

def _get_cluster_text(cluster) -> str:
    """Concatena todo el texto disponible del cluster para el análisis."""
    texts = []

    if cluster.representative_article:
        ra = cluster.representative_article
        texts.append(ra.title)
        texts.append(ra.summary)
        if hasattr(ra, "full_text") and ra.full_text:
            texts.append(ra.full_text[:2000])

    # Agregar títulos de otros artículos del cluster
    for article in cluster.articles[:10]:
        if article.id != (cluster.representative_article.id if cluster.representative_article else None):
            texts.append(article.title)

    return " ".join(texts)
