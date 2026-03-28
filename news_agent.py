"""
news_agent.py — Orquestador principal del Global News Agent.

Punto de entrada del sistema. Ejecuta el pipeline completo:
1. Ingesta de fuentes globales
2. Deduplicación y clustering por evento
3. Scoring editorial multidimensional
4. Ranking top 5
5. Generación automática de posts Coraline (fotos #1 y #2)
6. Output en múltiples formatos

Uso:
    python news_agent.py                    # Ejecución estándar
    python news_agent.py --dry-run          # Sin guardar archivos
    python news_agent.py --verbose          # Logs detallados
    python news_agent.py --top 10           # Top 10 en lugar de top 5
    python news_agent.py --max-tier 2       # Solo fuentes tier 1 y 2
    python news_agent.py --no-coraline      # Saltar generación de posts Coraline
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE LOGGING
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("news_agent.log", encoding="utf-8"),
        ],
    )


logger = logging.getLogger("GlobalNewsAgent")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def load_config(config_path: str = "config.json") -> dict:
    """Carga la configuración del sistema."""
    defaults = {
        "top_n": 5,
        "max_tier": 2,
        "output_dir": "output",
        "output_formats": ["json", "whatsapp", "email", "markdown"],
        "max_article_age_hours": 24,
        "min_article_words": 80,
        "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",
        "dbscan_eps": 0.18,
        "minhash_threshold": 0.85,
    }

    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        defaults.update(user_config)
        logger.info(f"Configuración cargada desde {config_path}")
    else:
        logger.info("Usando configuración por defecto (no se encontró config.json)")

    return defaults


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(config: dict, dry_run: bool = False) -> dict:
    """
    Ejecuta el pipeline completo de análisis de noticias.
    Retorna el output JSON con el top N.
    """
    start_time = time.time()
    output_dir = config["output_dir"]

    logger.info("=" * 70)
    logger.info("GLOBAL NEWS AGENT — INICIO DEL PIPELINE")
    logger.info(f"Fecha: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    logger.info("=" * 70)

    # ─── PASO 1: INGESTA ─────────────────────────────────────────────────────
    logger.info("\n[PASO 1/6] Ingesta de fuentes globales...")
    try:
        from ingestion import ingest_all_sources, print_ingestion_stats
        articles = ingest_all_sources(max_tier=config["max_tier"], verbose=True)
        total_articles = len(articles)
        logger.info(f"✓ {total_articles} artículos ingresados")
        if config.get("verbose"):
            print_ingestion_stats(articles)
    except Exception as e:
        logger.error(f"Error en ingesta: {e}")
        raise

    if total_articles == 0:
        logger.error("No se ingresaron artículos. Verificar conectividad y fuentes.")
        sys.exit(1)

    # ─── PASO 2: CLUSTERING ───────────────────────────────────────────────────
    logger.info("\n[PASO 2/6] Deduplicación y clustering por evento...")
    try:
        from clusterer import run_clustering_pipeline, print_cluster_stats
        clusters = run_clustering_pipeline(articles)
        real_clusters = [c for c in clusters if not c.is_noise]
        total_clusters = len(real_clusters)
        logger.info(f"✓ {total_clusters} eventos distintos identificados")
        if config.get("verbose"):
            print_cluster_stats(clusters)
    except Exception as e:
        logger.error(f"Error en clustering: {e}")
        raise

    # ─── PASO 3: SCORING ─────────────────────────────────────────────────────
    logger.info("\n[PASO 3/6] Scoring editorial multidimensional...")
    try:
        from scorer import get_top_n_diverse
        top_n = config.get("top_n", 5)
        top_results, excluded_results = get_top_n_diverse(real_clusters, n=top_n)
        logger.info(f"✓ Top {top_n} eventos rankeados (con diversidad temática y regional)")

        # Log del ranking
        logger.info("\n--- RANKING FINAL (con filtro de diversidad) ---")
        for i, (cluster, breakdown) in enumerate(top_results):
            logger.info(
                f"  #{i+1} [{breakdown.total_score:.1f}/100] [{breakdown.macrotema}] {cluster.event_label[:55]}..."
            )
        logger.info(f"  Excluidos por diversidad: {len(excluded_results)}")
        logger.info("-----------------------------------------------")
    except Exception as e:
        logger.error(f"Error en scoring: {e}")
        raise

    # ─── PASO 4: GENERACIÓN CORALINE ─────────────────────────────────────────
    coraline_posts = []
    generate_coraline = config.get("generate_coraline", True)

    if generate_coraline and not dry_run:
        logger.info("\n[PASO 4/6] Generando posts Coraline (noticias #1 y #2)...")
        try:
            from coraline_news_module import generate_posts as coraline_generate_posts
            coraline_posts = coraline_generate_posts(top_results, output_dir=output_dir)
            if coraline_posts:
                logger.info(f"✓ {len(coraline_posts)} post(s) Coraline generados:")
                for post in coraline_posts:
                    rank = post.get("rank", "?")
                    img = post.get("image_local_path") or post.get("image_url", "sin imagen")
                    logger.info(f"   • Noticia #{rank}: {img}")
            else:
                logger.info("ℹ️  No se generaron posts Coraline (revisar API keys o logs)")
        except ImportError:
            logger.warning("⚠️  coraline_news_module no disponible — omitiendo paso Coraline")
        except Exception as e:
            logger.error(f"⚠️  Error en generación Coraline (pipeline continúa): {e}")
    elif dry_run:
        logger.info("\n[PASO 4/6] Modo dry-run: omitiendo generación Coraline")
    else:
        logger.info("\n[PASO 4/6] Coraline desactivado (--no-coraline)")

    # ─── PASO 5: FORMATEO Y OUTPUT ────────────────────────────────────────────
    logger.info("\n[PASO 5/6] Generando outputs...")
    try:
        from formatter import save_all_formats, format_whatsapp

        if not dry_run:
            paths, wa_text = save_all_formats(
                top_results,
                output_dir=output_dir,
                total_articles=total_articles,
                total_clusters=total_clusters,
                excluded=excluded_results,
            )
            logger.info(f"✓ Archivos guardados en '{output_dir}/':")
            for fmt, path in paths.items():
                logger.info(f"   • {fmt}: {path}")
        else:
            logger.info("Modo dry-run: no se guardan archivos")
            wa_text = format_whatsapp(top_results)

    except Exception as e:
        logger.error(f"Error en formateo: {e}")
        raise

    # ─── PASO 6: RESUMEN FINAL ────────────────────────────────────────────────
    elapsed = time.time() - start_time

    logger.info("\n[PASO 6/6] Pipeline completado")
    logger.info("=" * 70)
    logger.info(f"Tiempo total: {elapsed:.1f}s")
    logger.info(f"Artículos procesados: {total_articles}")
    logger.info(f"Eventos identificados: {total_clusters}")
    if coraline_posts:
        logger.info(f"Posts Coraline generados: {len(coraline_posts)}")
    logger.info("=" * 70)

    # Imprimir output WhatsApp en consola
    print("\n" + "=" * 70)
    print("OUTPUT PARA WHATSAPP/TELEGRAM:")
    print("=" * 70)
    print(wa_text)
    print("=" * 70 + "\n")

    # Construir resultado para retorno
    result = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "elapsed_seconds": round(elapsed, 2),
        "articles_ingested": total_articles,
        "clusters_found": total_clusters,
        "top_events": [
            {
                "rank": i + 1,
                "event": cluster.event_label,
                "score": breakdown.total_score,
                "sources": cluster.unique_sources,
                "regions": cluster.unique_regions,
            }
            for i, (cluster, breakdown) in enumerate(top_results)
        ],
        "output_files": paths if not dry_run else {},
        "coraline_posts": coraline_posts,
    }

    return result


# ─────────────────────────────────────────────────────────────────────────────
# MODO DE PRUEBA — Sin dependencias externas
# ─────────────────────────────────────────────────────────────────────────────

def run_demo_mode():
    """
    Ejecuta el agente en modo demo con datos sintéticos.
    Útil para verificar que el sistema funciona sin conectividad.
    """
    print("\n🎭 MODO DEMO — Generando output de ejemplo con datos sintéticos\n")

    # Datos de ejemplo que simulan el output del pipeline real
    demo_events = [
        {
            "event": "Russia launches major offensive in eastern Ukraine, NATO calls emergency session",
            "score": 89.5,
            "sources": ["Reuters", "BBC", "Al Jazeera", "Der Spiegel", "Kyiv Independent", "Le Monde"],
            "regions": ["europe_west", "europe_east", "middle_east_north_africa", "global"],
            "category": "CONFLICTO",
            "summary": "Russian forces launched a large-scale offensive across three fronts in eastern Ukraine, with NATO foreign ministers convening an emergency session in Brussels. Casualties are reported in Kharkiv and Zaporizhzhia. US Secretary of State en route to Kyiv.",
            "boosts": ["armed_conflict_active (+15)", "un_security_council_emergency (+8)"],
            "why": "Cubierto por 6 medios independientes en 4 regiones. Alto impacto geopolítico (9.5/10). Boost contextual: conflicto armado activo, sesión de emergencia ONU."
        },
        {
            "event": "IMF warns of global recession risk as US-China trade war escalates with new 200% tariffs",
            "score": 82.1,
            "sources": ["Financial Times", "Nikkei Asia", "Reuters", "Le Monde", "South China Morning Post"],
            "regions": ["global", "asia_pacific", "europe_west", "americas"],
            "category": "ECONOMÍA GLOBAL",
            "summary": "The IMF downgraded global growth forecasts to 1.8%, citing the escalating US-China trade conflict after Washington announced 200% tariffs on Chinese semiconductors. Asian markets fell 3-4%, with the yuan reaching a 15-year low against the dollar.",
            "boosts": ["financial_systemic_crisis (+12)", "multilateral_sanctions (+7)"],
            "why": "Cubierto por 5 medios en 4 regiones. Alto impacto económico (8.8/10). Efecto directo en mercados globales. Crisis en curso hace 4 días."
        },
        {
            "event": "WHO declares mpox strain outbreak in Central Africa a Public Health Emergency of International Concern",
            "score": 76.3,
            "sources": ["WHO", "Reuters", "The Guardian", "AllAfrica", "BBC"],
            "regions": ["global", "africa_sub_saharan", "europe_west"],
            "category": "SALUD GLOBAL",
            "summary": "The World Health Organization declared a new mpox variant spreading through five Central African nations a Public Health Emergency of International Concern (PHEIC), the highest alert level. The strain shows higher transmissibility than previous variants. 12 countries have reported imported cases.",
            "boosts": ["pandemic_outbreak (+18)"],
            "why": "OMS declaración oficial de emergencia. Cobertura en 3 regiones. Alta relevancia institucional (9/10). Evento nuevo con potencial de expansión global."
        },
        {
            "event": "Saudi Arabia and Iran sign mutual defense pact, reshaping Middle East security architecture",
            "score": 71.8,
            "sources": ["Al Jazeera", "Reuters", "Haaretz", "Nikkei Asia", "The Economist"],
            "regions": ["middle_east_north_africa", "asia_pacific", "global", "europe_west"],
            "category": "GEOPOLÍTICA",
            "summary": "Saudi Arabia and Iran formalized a landmark mutual defense agreement in Beijing, mediated by China. The deal, if implemented, would constitute the most significant realignment of Middle Eastern alliances since the 1979 Iranian Revolution, with implications for US military posture in the Gulf.",
            "boosts": ["regime_change (+10)"],
            "why": "Cubierto por 5 medios en 4 regiones. Impacto geopolítico histórico (9/10). Involucra potencias regionales y mediación china."
        },
        {
            "event": "Major 8.2 earthquake strikes coastal Japan, tsunami warnings across Pacific",
            "score": 68.9,
            "sources": ["NHK World", "Reuters", "AP", "The Straits Times", "BBC"],
            "regions": ["asia_pacific", "global", "americas", "europe_west"],
            "category": "HUMANITARIO",
            "summary": "A magnitude 8.2 earthquake struck off the coast of Hokkaido, Japan, triggering Pacific-wide tsunami warnings reaching the coasts of Hawaii, Chile and New Zealand. Japanese authorities have ordered evacuation of 2.1 million residents in coastal areas. First waves reported at 1.5 meters.",
            "boosts": ["major_natural_disaster (+8)"],
            "why": "Cubierto por 5 medios en 4 regiones. Alta severidad (9/10). Alcance geográfico intercontinental. Afecta a millones de personas en tiempo real."
        },
    ]

    from formatter import RANK_EMOJIS, _get_category_emoji
    from datetime import datetime

    date = datetime.now().strftime("%d %b %Y")

    print("=" * 70)
    print(f"🌍 TOP 5 NOTICIAS GLOBALES — {date} (DEMO)")
    print("Sistema editorial autónomo | No por viralidad, sino por importancia")
    print("=" * 70)

    for i, event in enumerate(demo_events):
        rank_emoji = RANK_EMOJIS[i]
        print(f"\n{rank_emoji} [{event['category']}] {event['event']}")
        print(f"   Score: {event['score']:.1f}/100 | {len(event['sources'])} medios | {len(event['regions'])} regiones")
        print(f"   {event['summary'][:150]}...")
        print(f"   📰 {' · '.join(event['sources'][:4])}")
        print(f"   💡 {event['why']}")

    print("\n" + "=" * 70)
    print("NOTA: Este es un ejemplo sintético. Para datos reales, ejecutar sin --demo")
    print("=" * 70 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# ARGUMENTOS DE LÍNEA DE COMANDOS
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Global News Agent — Top 5 noticias más importantes del mundo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python news_agent.py                   # Ejecución estándar (incluye Coraline)
  python news_agent.py --demo            # Modo demo con datos sintéticos
  python news_agent.py --dry-run         # Sin guardar archivos
  python news_agent.py --no-coraline     # Solo noticias, sin generar posts Coraline
  python news_agent.py --top 10          # Top 10 en lugar de top 5
  python news_agent.py --verbose         # Logs detallados
  python news_agent.py --max-tier 1      # Solo fuentes tier 1 (agencias top)
        """,
    )

    parser.add_argument("--demo", action="store_true",
                        help="Ejecutar en modo demo con datos sintéticos")
    parser.add_argument("--dry-run", action="store_true",
                        help="Ejecutar sin guardar archivos en disco")
    parser.add_argument("--verbose", action="store_true",
                        help="Mostrar logs detallados")
    parser.add_argument("--top", type=int, default=5,
                        help="Número de eventos a rankear (default: 5)")
    parser.add_argument("--max-tier", type=int, default=2,
                        help="Tier máximo de fuentes (1=solo top, 2=standard, 3=all)")
    parser.add_argument("--output-dir", type=str, default="output",
                        help="Directorio para guardar los outputs")
    parser.add_argument("--config", type=str, default="config.json",
                        help="Ruta al archivo de configuración")
    parser.add_argument("--no-coraline", action="store_true",
                        help="Omitir generación de posts Coraline (más rápido, sin API calls)")

    return parser.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
# PUNTO DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = parse_args()
    setup_logging(verbose=args.verbose)

    if args.demo:
        run_demo_mode()
        sys.exit(0)

    # Cargar config
    config = load_config(args.config)

    # Override con args de línea de comandos
    if args.top:
        config["top_n"] = args.top
    if args.max_tier:
        config["max_tier"] = args.max_tier
    if args.output_dir:
        config["output_dir"] = args.output_dir
    if args.verbose:
        config["verbose"] = True
    if args.no_coraline:
        config["generate_coraline"] = False

    try:
        result = run_pipeline(config, dry_run=args.dry_run)
        print(f"\n✅ Pipeline completado en {result['elapsed_seconds']}s")
        sys.exit(0)
    except KeyboardInterrupt:
        logger.info("Pipeline interrumpido por el usuario")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error fatal en el pipeline: {e}", exc_info=True)
        sys.exit(1)
