# Global News Intelligence Agent
## Arquitectura, Lógica de Ranking y Plan de Implementación

---

## 1. OBJETIVO DEL SISTEMA

Construir un agente autónomo que, cada día, identifique las **5 noticias más importantes del mundo** según criterios editoriales de relevancia internacional sustantiva — no por popularidad, clicks ni viralidad.

---

## 2. REPOSITORIOS ANALIZADOS

### 2.1 Ingesta de Noticias

| Repositorio | Stars | Licencia | Pros | Contras |
|---|---|---|---|---|
| **newspaper4k** (AndyTheFactory/newspaper4k) | ~4k | MIT | Soporta 80+ idiomas, multithread, extrae texto limpio | Falla en sitios con JS pesado |
| **news-please** (fhamborg/news-please) | ~3k | Apache 2.0 | Crawler completo (Scrapy+Newspaper+Readability), soporte archivos | Setup más complejo |
| **feedparser** (kurtmckee/feedparser) | ~2k | BSD | Estándar para RSS/Atom, battle-tested, maneja edge cases | Solo parsea feeds, no scrape |
| **pygooglenews** (kotartemiy/pygooglenews) | ~1.5k | MIT | Acceso fácil a Google News por región/idioma | Unofficial API, frágil ante cambios de Google |
| **newscatcher** (NewscatcherAPI) | ~800 | MIT/Prop. | Cobertura casi universal de sitios | API premium para producción |

### 2.2 Deduplicación y Clustering

| Repositorio | Stars | Licencia | Pros | Contras |
|---|---|---|---|---|
| **datasketch** (MinHashLSH) | ~4k | MIT | MinHash + LSH para detección near-duplicate a escala | Requiere tuning del umbral |
| **sentence-transformers** (UKPLab) | ~16k | Apache 2.0 | Embeddings multilingüe, 100+ idiomas, SOTA | Requiere GPU para volumen alto |
| **scikit-learn** DBSCAN/AgglomerativeClustering | ~60k | BSD | Clustering robusto, sin necesidad de K predefinido | No especializado en noticias |
| **text-dedup** (ChenghaoMou) | ~2k | MIT | MinHash, SimHash, Bloom Filter integrados | No específico para noticias |

### 2.3 Scoring e Importancia Editorial

> ⚠️ HALLAZGO CRÍTICO: No existe ningún sistema open-source que score noticias por importancia geopolítica. Esta capa debe construirse custom.

| Repositorio | Stars | Licencia | Pros | Contras |
|---|---|---|---|---|
| **GDELT Project** + gdeltPyR | Free | Libre | 300+ categorías CAMEO de eventos, actualización cada 15 min, 1979-presente | Scoring por frecuencia, no por importancia real |
| **MediaCloud** (mediacloud/backend) | ~500 | AGPL-3.0 | Métricas de cobertura cross-outlet, foco editorial | Infraestructura compleja, no es una librería |
| **spaCy** (explosion/spaCy) | ~30k | MIT | NER en 70+ idiomas, extracción de entidades geopolíticas | No puntúa importancia por sí solo |
| **ranx** (AmenRa/ranx) | ~1k | MIT | Evaluación de rankers (NDCG, Spearman, etc.) | Solo evaluación, no ranking |

### 2.4 RECOMENDACIÓN DE BASE TÉCNICA

**Stack recomendado (Opción Híbrida):**

```
Ingesta:     feedparser + newspaper4k + pygooglenews
Clustering:  sentence-transformers (multilingual) + DBSCAN
Scoring:     GDELT (señal base) + Custom scorer (capa editorial)
NER:         spaCy multilingüe
Output:      JSON + Markdown formateado
```

**Por qué esta combinación:**
- Feedparser es la opción más confiable y liviana para RSS
- sentence-transformers resuelve el problema multilingüe de un solo golpe (paraphrase-multilingual-MiniLM-L12-v2)
- El scorer custom es inevitable: nadie ha resuelto esto antes, y es la parte más valiosa del sistema
- GDELT provee señales objetivas de magnitud del evento (sin ser proxy de viralidad)

---

## 3. ARQUITECTURA DEL SISTEMA

```
╔══════════════════════════════════════════════════════════════╗
║                    GLOBAL NEWS AGENT                         ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  ┌─────────────────────────────────────────────────────┐    ║
║  │  CAPA 1: INGESTA                                    │    ║
║  │  ┌──────────┐ ┌──────────┐ ┌──────────┐            │    ║
║  │  │ RSS Feed │ │ Web Scrp │ │ GDELT    │            │    ║
║  │  │ (60+     │ │newspaper │ │ API      │            │    ║
║  │  │  fuentes)│ │ 4k       │ │          │            │    ║
║  │  └────┬─────┘ └────┬─────┘ └────┬─────┘            │    ║
║  │       └────────────┴────────────┘                   │    ║
║  │                    ↓                                │    ║
║  │         [Pool normalizado de artículos]              │    ║
║  └─────────────────────────────────────────────────────┘    ║
║                         ↓                                    ║
║  ┌─────────────────────────────────────────────────────┐    ║
║  │  CAPA 2: LIMPIEZA Y NORMALIZACIÓN                   │    ║
║  │  - Eliminar duplicados exactos (hash MD5 de título) │    ║
║  │  - Detectar idioma                                  │    ║
║  │  - Normalizar fechas → UTC                          │    ║
║  │  - Filtrar artículos >24h o <50 palabras            │    ║
║  └─────────────────────────────────────────────────────┘    ║
║                         ↓                                    ║
║  ┌─────────────────────────────────────────────────────┐    ║
║  │  CAPA 3: CLUSTERING POR EVENTO                      │    ║
║  │  - Embeddings multilingüe (sentence-transformers)   │    ║
║  │  - DBSCAN para agrupar artículos del mismo evento   │    ║
║  │  - Umbral: cosine similarity > 0.82                 │    ║
║  │  - Output: N clusters = N eventos distintos         │    ║
║  └─────────────────────────────────────────────────────┘    ║
║                         ↓                                    ║
║  ┌─────────────────────────────────────────────────────┐    ║
║  │  CAPA 4: SCORING EDITORIAL (núcleo del sistema)     │    ║
║  │  - 7 dimensiones de importancia (ver sección 4)     │    ║
║  │  - Score = suma ponderada de dimensiones            │    ║
║  │  - Penalización anti-sesgo anglocéntrico            │    ║
║  └─────────────────────────────────────────────────────┘    ║
║                         ↓                                    ║
║  ┌─────────────────────────────────────────────────────┐    ║
║  │  CAPA 5: RANKING Y OUTPUT                           │    ║
║  │  - Top 5 eventos por score                          │    ║
║  │  - Representante por cluster (mejor artículo)       │    ║
║  │  - Explicación del score por dimensión              │    ║
║  │  - Output JSON + Email/WhatsApp                     │    ║
║  └─────────────────────────────────────────────────────┘    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 4. LÓGICA DE SCORING — ESQUEMA DE PUNTUACIÓN

Cada evento recibe un score de 0 a 100 basado en 7 dimensiones.

### 4.1 Dimensiones y Pesos

```
SCORE_TOTAL = Σ (peso_i × valor_i) donde valor_i ∈ [0, 10]

Dimensión                        Peso   Justificación
─────────────────────────────────────────────────────────────
1. Impacto geopolítico           25%    Guerras, tratados, elecciones mayores,
                                        cambios de régimen, sanciones
2. Impacto económico global      20%    Movimiento de mercados, crisis deuda,
                                        sanciones comerciales, colapso monedas
3. Alcance geográfico            15%    ¿Cuántos países/regiones afectados?
                                        (local=0, global=10)
4. Severidad / Urgencia          15%    Muertes, desastres, conflictos armados,
                                        pandemias, decisiones irreversibles
5. Diversidad de fuentes         10%    N unique outlets + diversidad regional
                                        (ej: cobertura en 3+ continentes = max)
6. Persistencia del tema         10%    ¿Es noticia nueva o continuación de evento
                                        mayor? (ongoing crisis sube el score)
7. Relevancia institucional       5%    ONU, G7/G20, FMI, OTAN, WHO, OPEC, etc.
─────────────────────────────────────────────────────────────
TOTAL                           100%
```

### 4.2 Filtros de exclusión automática (score = 0 forzado)

- Noticias de entretenimiento / cultura pop sin consecuencias políticas
- Deportes (salvo dopaje estatal o boicot olímpico con implicancias geopolíticas)
- Tendencias de redes sociales
- Noticias de un solo país sin efecto internacional documentado
- Artículos con <3 fuentes independientes

### 4.3 Boosts contextuales

```python
BOOSTS = {
    "armed_conflict": +15,        # Conflicto armado activo o escalada
    "nuclear_risk": +20,          # Riesgo nuclear explícito
    "pandemic_outbreak": +18,     # Nuevo brote o pandemia declarada
    "financial_crisis": +12,      # Crisis financiera sistémica
    "regime_change": +10,         # Cambio de gobierno o golpe
    "natural_disaster_major": +8, # Desastre natural >1000 afectados
    "un_security_council": +8,    # Sesión de emergencia Consejo de Seguridad
    "sanctions_major": +7,        # Sanciones económicas multilaterales
}
```

---

## 5. FUENTES POR REGIÓN (anti-sesgo anglocéntrico)

### Estrategia de diversificación regional

El sistema asigna **cuotas de ingesta por región**. Ninguna región puede aportar más del 35% del pool inicial.

```
REGIÓN                FUENTES INCLUIDAS                              IDIOMA
──────────────────────────────────────────────────────────────────────────
Europa Occidental     Reuters, BBC, Le Monde, Der Spiegel, El País  Multi
Europa del Este       Euractiv, Kyiv Independent, Meduza             Multi
Medio Oriente/N.Áf.   Al Jazeera EN, Al-Monitor, Haaretz             EN/AR
Asia-Pacífico         South China Morning Post, NHK World, The Hindu  EN
África Sub-Sahariana  AllAfrica, Daily Maverick, The East African    EN
América Latina        Folha de S.Paulo, La Nación, Infobae Int'l     ES/PT
América del Norte     AP, The Guardian US, NPR                       EN
Global/Multilateral   GDELT, UN News, Devex, Foreign Policy          EN
```

### Penalización de homogeneidad regional

```python
def penalizar_sesgo_regional(cluster):
    fuentes_por_region = contar_por_region(cluster.articulos)
    region_dominante = max(fuentes_por_region.values())
    total_fuentes = sum(fuentes_por_region.values())

    if region_dominante / total_fuentes > 0.6:
        # Una región domina >60% → reducir score
        cluster.score *= 0.75

    if len(fuentes_por_region) == 1:
        # Solo una región → penalización fuerte
        cluster.score *= 0.5
```

---

## 6. ESQUEMA DE DATOS

### 6.1 Artículo normalizado

```json
{
  "id": "sha256_del_titulo_y_url",
  "title": "China and US reach preliminary trade agreement",
  "url": "https://reuters.com/...",
  "source": "Reuters",
  "source_region": "global",
  "source_tier": 1,
  "language": "en",
  "published_at": "2026-03-28T14:32:00Z",
  "ingested_at": "2026-03-28T15:00:00Z",
  "summary": "...",
  "full_text": "...",
  "entities": {
    "countries": ["China", "United States"],
    "organizations": ["WTO", "US Trade Representative"],
    "people": ["Xi Jinping", "Scott Bessent"]
  },
  "embedding": [0.23, -0.14, ...]
}
```

### 6.2 Cluster / Evento

```json
{
  "cluster_id": "evt_20260328_001",
  "event_label": "US-China trade deal preliminary agreement",
  "article_count": 47,
  "source_count": 23,
  "regions_covered": ["north_america", "east_asia", "europe"],
  "articles": ["id1", "id2", "..."],
  "representative_article": "id1",
  "first_seen": "2026-03-28T06:00:00Z",
  "is_ongoing": true,
  "days_active": 3
}
```

### 6.3 Score breakdown

```json
{
  "cluster_id": "evt_20260328_001",
  "total_score": 82.4,
  "rank": 1,
  "score_breakdown": {
    "geopolitical_impact": {"raw": 9.0, "weight": 0.25, "contribution": 22.5},
    "economic_impact":     {"raw": 8.5, "weight": 0.20, "contribution": 17.0},
    "geographic_reach":    {"raw": 8.0, "weight": 0.15, "contribution": 12.0},
    "severity_urgency":    {"raw": 6.0, "weight": 0.15, "contribution": 9.0},
    "source_diversity":    {"raw": 9.0, "weight": 0.10, "contribution": 9.0},
    "topic_persistence":   {"raw": 8.0, "weight": 0.10, "contribution": 8.0},
    "institutional_rel":   {"raw": 7.0, "weight": 0.05, "contribution": 3.5},
    "boosts_applied": ["financial_crisis"],
    "boost_total": 12.0,
    "regional_penalty": 0
  },
  "why_top5": "Cubre 3 continentes con 23 fuentes diversas. Evento económico de primer orden con impacto en mercados globales. Lleva 3 días activo como crisis comercial en curso.",
  "why_not_excluded": "Tiene cobertura en Asia, Europa y América. Más de 20 outlets independientes."
}
```

### 6.4 Output final JSON

```json
{
  "date": "2026-03-28",
  "generated_at": "2026-03-28T23:00:00Z",
  "pipeline_version": "1.0.0",
  "articles_ingested": 1247,
  "clusters_identified": 89,
  "top5": [
    {
      "rank": 1,
      "event": "US-China preliminary trade agreement",
      "summary": "...",
      "score": 82.4,
      "sources": ["Reuters", "South China Morning Post", "Der Spiegel", "..."],
      "url_principal": "https://reuters.com/...",
      "why": "...",
      "score_breakdown": {...}
    }
  ]
}
```

---

## 7. OUTPUT LEGIBLE — EMAIL / WHATSAPP

### Formato WhatsApp

```
🌍 *TOP 5 NOTICIAS GLOBALES — 28 Mar 2026*
_Sistema editorial autónomo | No por viralidad, sino por importancia_

━━━━━━━━━━━━━━━━━━━━━━
🥇 *[ECONOMÍA GLOBAL] EEUU y China acuerdan tregua comercial*
Score: 82/100 | 23 medios | 3 continentes

China y Estados Unidos alcanzaron un acuerdo preliminar para suspender los aranceles escalados desde enero. El yuan subió 0.8% y el S&P 500 cerró en máximos de mes. Negociaciones continúan en Ginebra.

📰 Reuters · SCMP · Financial Times · NHK World
━━━━━━━━━━━━━━━━━━━━━━
🥈 *[CONFLICTO] Escalada en el Mar Rojo: nuevo ataque a buque europeo*
Score: 78/100 | 18 medios | 4 continentes
...
━━━━━━━━━━━━━━━━━━━━━━
🥉 *[SALUD GLOBAL] OMS declara alerta por brote de influenza H5N2*
...
━━━━━━━━━━━━━━━━━━━━━━
4️⃣ *[GEOPOLÍTICA] Rusia suspende acuerdo de granos del Mar Negro*
...
━━━━━━━━━━━━━━━━━━━━━━
5️⃣ *[ENERGÍA] OPEC+ recorta producción 1.2M barriles/día extra*
...
━━━━━━━━━━━━━━━━━━━━━━
🤖 Sistema procesó 1,247 artículos → 89 eventos → top 5
⚙️ Anti-sesgo regional activo | Fuentes: 6 regiones del mundo
```

---

## 8. PLAN DE IMPLEMENTACIÓN

### FASE 1 — MVP (Semana 1-2)

**Objetivo:** Proof of concept funcional que entregue top 5 diario

```
Día 1-2: Setup
  ✓ Instalar dependencias (ver requirements.txt)
  ✓ Configurar sources.py con 20 feeds RSS iniciales
  ✓ Verificar ingesta básica con feedparser

Día 3-4: Pipeline core
  ✓ ingestion.py → fetching + normalización
  ✓ clusterer.py → hash dedup + embeddings básicos
  ✓ scorer.py → scoring manual con pesos fijos

Día 5-7: Output y tests
  ✓ formatter.py → JSON + WhatsApp format
  ✓ news_agent.py → orquestador completo
  ✓ Test manual: correr el agente y evaluar top 5 contra criterio humano
```

**Stack MVP:**
- Python 3.11+
- feedparser (RSS)
- newspaper4k (scraping)
- sentence-transformers (embeddings — modelo: paraphrase-multilingual-MiniLM-L12-v2)
- scikit-learn (DBSCAN clustering)
- spaCy + modelos multilingual (NER)
- Anthropic Claude API (evaluación editorial final — capa LLM)

### FASE 2 — Versión robusta (Semana 3-6)

```
Semana 3: Anti-sesgo y diversidad
  - Implementar cuotas por región
  - Añadir fuentes en árabe, chino, ruso, portugués
  - Integrar GDELT como señal base de eventos geopolíticos

Semana 4: Scoring avanzado
  - Fine-tuning del scorer contra benchmark humano
  - Implementar boosts contextuales dinámicos
  - Agregar detección de "persistencia de tema" cross-day

Semana 5: Automatización
  - Cron job o GitHub Actions para ejecución diaria (06:00 UTC)
  - Output a archivo JSON diario + envío por email/WhatsApp
  - Dashboard HTML simple para revisión

Semana 6: Evaluación
  - Comparar top 5 del sistema vs. top 5 manual de Reuters/FT/AP
  - Calcular precision@5 durante 2 semanas
  - Ajustar pesos del scorer según resultados
```

### FASE 3 — Producción (Mes 2+)

```
- API propia para consultar el ranking
- Interfaz web con historial de noticias
- Alertas por evento crítico (score > 90) en tiempo real
- Fine-tuning de modelo de scoring con datos históricos etiquetados
- Integración con Slack / Telegram / Email automático
```

---

## 9. CÓMO EVITAR EL SESGO ANGLOCÉNTRICO

El sistema implementa 4 mecanismos complementarios:

1. **Cuotas de ingesta regional**: Ninguna región puede aportar >35% del pool
2. **Diversidad de fuentes como dimensión de score**: Eventos cubiertos solo por medios anglosajones reciben score reducido
3. **Fuentes en idioma original**: Se procesan artículos en árabe, chino, francés, portugués, alemán, español, ruso — traducidos mediante sentence-transformers multilingual para el clustering (sin pérdida semántica)
4. **Penalización de homogeneidad regional**: Clusters donde el 60%+ de artículos viene de una sola región son penalizados en su score total

---

## 10. ESTRUCTURA DE ARCHIVOS

```
INFLUENCER/global_news_agent/
│
├── ARQUITECTURA.md          ← Este documento
├── news_agent.py            ← Orquestador principal (punto de entrada)
├── sources.py               ← Fuentes RSS curadas por región
├── ingestion.py             ← Fetching, parsing y normalización
├── clusterer.py             ← Deduplicación y clustering por evento
├── scorer.py                ← Motor de scoring editorial
├── formatter.py             ← Output JSON + WhatsApp/email
├── config.json              ← Configuración del sistema
├── requirements.txt         ← Dependencias Python
├── run_daily.sh             ← Script de ejecución diaria
└── output/                  ← Resultados diarios (generado automáticamente)
    ├── 2026-03-28.json
    └── 2026-03-28_whatsapp.txt
```
