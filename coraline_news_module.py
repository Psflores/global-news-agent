"""
coraline_news_module.py — Integración del News Agent con el pipeline de Coraline Jones.

Flujo:
1. Recibe el top 5 del news agent
2. Toma la noticia #1 y #2
3. Elige la escena de Coraline más apropiada para cada noticia
4. Genera dos imágenes nuevas de Coraline via Higgsfield (Seedream v4)
5. Redacta un caption en voz de Coraline (español, voseo rioplatense)
   conectando la noticia global con su nicho: patrimonio, riesgo, contratos
6. Entrega un paquete de post listo para revisión humana antes de publicar

IMPORTANTE: Nunca publica automáticamente. Siempre requiere aprobación humana.
"""

import sys
import os
import json
import time
import httpx
import requests
from datetime import datetime, timezone
from pathlib import Path

# Agregar el pipeline de Coraline al path para reusar su config y credenciales
CORALINE_PIPELINE_DIR = Path(__file__).parent.parent / "CORALINE_pipeline"
sys.path.insert(0, str(CORALINE_PIPELINE_DIR / "pipeline"))

try:
    from config import (
        HF_API_KEY, HF_API_SECRET,
        HF_BASE_URL, HF_IMAGE_APP,
        CORALINE_PROMPT,
        ANTHROPIC_API_KEY,
    )
    HAS_PIPELINE_CONFIG = True
except ImportError:
    # Fallback si no se puede importar el config del pipeline
    HF_API_KEY    = "2a5b16cd-b085-46f7-b763-ec384b238a5e"
    HF_API_SECRET = "806f7e856eb7c1dd7314bf164d2b81ee5bb3347420c8aa26371c21f2b53076ed"
    HF_BASE_URL   = "https://platform.higgsfield.ai"
    HF_IMAGE_APP  = "bytedance/seedream/v4/text-to-image"
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    CORALINE_PROMPT = """Photorealistic portrait of a 35-year-old Argentine woman named Coraline Jones.
Physical traits: olive-warm skin tone, dark brown almost black hair (usually pulled
back in a low chignon or sleek bun), sharp symmetrical facial features, strong
defined jawline, almond-shaped dark brown eyes with subtle cat-eye liner,
neutral-to-serious expression, minimal makeup (nude lips, defined brows).
Always wearing black or dark navy clothing — blazers, turtlenecks, structured outfits.
Aesthetic: editorial, cinematic, high contrast lighting, sophisticated.
No smiling. Calm, observant, authoritative presence.
Color palette: black, ivory, stone grey, dark green accents."""
    HAS_PIPELINE_CONFIG = False

HF_HEADERS = {
    "Authorization": f"Key {HF_API_KEY}:{HF_API_SECRET}",
    "Content-Type": "application/json",
    "User-Agent": "higgsfield-client-py/1.0",
}


# ─────────────────────────────────────────────────────────────────────────────
# ESCENAS DE CORALINE — Se elige según la categoría de la noticia
# ─────────────────────────────────────────────────────────────────────────────

SCENE_VARIANTS = {
    "ventana_noche": {
        "prompt_add": "standing by floor-to-ceiling window at night, city lights below, "
                      "reflective mood, watching the world from above, dark ambient light",
        "categories": ["CONFLICTO", "GUERRA", "HUMANITARIO", "NUCLEAR"],
        "mood": "observadora del mundo",
    },
    "sala_reunion": {
        "prompt_add": "head of minimalist conference table, cool blue lighting, "
                      "documents in front of her, corporate boardroom, serious focus",
        "categories": ["ECONOMÍA GLOBAL", "MERCADOS", "SANCIONES", "GEOPOLÍTICA"],
        "mood": "analítica, al mando",
    },
    "escritorio_legal": {
        "prompt_add": "seated at a dark minimalist desk, open laptop, "
                      "legal documents and pen nearby, city skyline through window, "
                      "dramatic side lighting",
        "categories": ["INTERNACIONAL", "DIPLOMACIA", "INSTITUCIONES"],
        "mood": "trabajando el criterio",
    },
    "lobby_corporativo": {
        "prompt_add": "standing in marble-floored corporate lobby, "
                      "golden hour backlight through glass facade, "
                      "coat over shoulders, commanding presence",
        "categories": ["ELECCIONES", "ENERGÍA"],
        "mood": "presencia ejecutiva",
    },
    "cafe_nocturno": {
        "prompt_add": "black and white photography style, Parisian-style café, "
                      "steam rising from espresso cup, open notebook, "
                      "quiet focus, late night",
        "categories": ["SALUD GLOBAL", "PANDEMIA"],
        "mood": "reflexión nocturna",
    },
    "retrato_cercano": {
        "prompt_add": "close-up portrait, studio high-contrast lighting, "
                      "dark fabric background, direct gaze at camera, "
                      "strong jawline emphasis, editorial photography",
        "categories": [],  # Escena default
        "mood": "presencia directa",
    },
}

NEGATIVE_PROMPT = (
    "smiling, cheerful, casual clothing, colorful, blonde, blue eyes, "
    "tattoos, warm tones, happy expression, beach, vacation, lifestyle"
)


# ─────────────────────────────────────────────────────────────────────────────
# SELECCIÓN DE ESCENA
# ─────────────────────────────────────────────────────────────────────────────

def select_scene(category: str, rank: int) -> dict:
    """
    Elige la escena más apropiada para Coraline según la categoría de la noticia.
    Si es la misma categoría para #1 y #2, usa escenas distintas.

    rank=1 → escena principal
    rank=2 → escena alternativa (diferente a la del #1)
    """
    cat_upper = category.upper()
    matched_scene = None
    scene_key = None

    for key, scene in SCENE_VARIANTS.items():
        for cat in scene["categories"]:
            if cat in cat_upper or cat_upper in cat:
                matched_scene = scene
                scene_key = key
                break
        if matched_scene:
            break

    # Default si no matchea ninguna categoría
    if not matched_scene:
        scene_key = "retrato_cercano"
        matched_scene = SCENE_VARIANTS["retrato_cercano"]

    # Para el #2: si matcheó la misma escena que habría usado para #1,
    # usar una escena alternativa. Esto se maneja en generate_posts()
    return {"key": scene_key, **matched_scene}


# ─────────────────────────────────────────────────────────────────────────────
# GENERACIÓN DE IMAGEN — Higgsfield Seedream v4
# ─────────────────────────────────────────────────────────────────────────────

def build_image_prompt(scene: dict, news_context: str = "") -> str:
    """
    Construye el prompt completo para generar la imagen de Coraline.
    Combina: prompt maestro + escena + contexto de la noticia.
    """
    base = CORALINE_PROMPT.strip()
    scene_add = scene["prompt_add"]

    # El contexto de la noticia NO aparece en el prompt (no queremos texto en la imagen)
    # Solo afecta levemente el mood/luz de la escena
    return f"{base}, {scene_add}. Ultra-realistic, 8K, editorial magazine quality."


def generate_coraline_image(scene: dict, news_context: str = "", aspect_ratio: str = "1:1") -> dict:
    """
    Genera una imagen de Coraline via Higgsfield Seedream v4.
    Retorna dict con url, request_id y metadatos.

    aspect_ratio: "1:1" (Instagram feed) | "9:16" (Stories/TikTok/Reels)
    """
    prompt = build_image_prompt(scene, news_context)

    print(f"\n🎨 Generando imagen de Coraline [{scene['key']}] — {aspect_ratio}")
    print(f"   Mood: {scene['mood']}")

    try:
        r = httpx.post(
            f"{HF_BASE_URL}/{HF_IMAGE_APP}",
            headers=HF_HEADERS,
            json={
                "prompt": prompt,
                "negative_prompt": NEGATIVE_PROMPT,
                "resolution": "2K",
                "aspect_ratio": aspect_ratio,
                "camera_fixed": True,
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()

        request_id = data.get("request_id")
        status_url = data.get("status_url")

        print(f"   Request ID: {request_id} — esperando generación...")

        # Polling hasta que la imagen esté lista
        image_url = _poll_higgsfield(status_url, request_id, max_wait=120)

        if image_url:
            print(f"   ✅ Imagen generada: {image_url[:60]}...")
            return {
                "success": True,
                "url": image_url,
                "request_id": request_id,
                "scene": scene["key"],
                "mood": scene["mood"],
                "prompt_preview": prompt[:100] + "...",
            }
        else:
            print(f"   ⚠️ Timeout en generación — usando imagen existente como fallback")
            return _fallback_image(scene["key"])

    except Exception as e:
        print(f"   ❌ Error Higgsfield: {e}")
        return _fallback_image(scene["key"])


def _poll_higgsfield(status_url: str, request_id: str, max_wait: int = 120) -> str:
    """Polling de Higgsfield hasta obtener la imagen generada."""
    elapsed = 0
    interval = 3

    while elapsed < max_wait:
        time.sleep(interval)
        elapsed += interval

        try:
            r = httpx.get(status_url, headers=HF_HEADERS, timeout=15)
            if not r.is_success:
                continue

            data = r.json()
            status = data.get("status", "").lower()

            if status in ("completed", "success", "done"):
                # Buscar la URL de la imagen en varias ubicaciones posibles
                for key in ("url", "image_url", "output_url", "result_url"):
                    if key in data and data[key]:
                        return data[key]
                # Buscar en output/outputs
                if "output" in data:
                    out = data["output"]
                    if isinstance(out, str):
                        return out
                    if isinstance(out, dict):
                        return out.get("url", out.get("image_url", ""))
                    if isinstance(out, list) and out:
                        return out[0] if isinstance(out[0], str) else out[0].get("url", "")

            elif status in ("failed", "error"):
                print(f"   ❌ Higgsfield reportó error: {data.get('error', 'desconocido')}")
                return ""

            # Aún procesando
            if elapsed % 15 == 0:
                print(f"   ⏳ Generando... ({elapsed}s / {max_wait}s)")

        except Exception:
            pass

    return ""


def _fallback_image(scene_key: str) -> dict:
    """
    Fallback cuando Higgsfield falla: usa una imagen existente de Coraline
    del CDN (ya generadas previamente).
    """
    existing_images = {
        "ventana_noche":    "https://d3u0tzju9qaucj.cloudfront.net/e88f2015-c160-4b7e-b0bd-77bca1c4a52a/b9ee7e58-35dc-4505-bc75-49034d65b8c4.jpeg",
        "sala_reunion":     "https://d3u0tzju9qaucj.cloudfront.net/e88f2015-c160-4b7e-b0bd-77bca1c4a52a/e64ef43a-9d1b-4636-b80c-b6a9fd2ff043.jpeg",
        "escritorio_legal": "https://d3u0tzju9qaucj.cloudfront.net/e88f2015-c160-4b7e-b0bd-77bca1c4a52a/6ed380cb-95ab-45b9-9175-78021250215d.jpeg",
        "lobby_corporativo":"https://d3u0tzju9qaucj.cloudfront.net/e88f2015-c160-4b7e-b0bd-77bca1c4a52a/56c23e44-bae2-426a-9764-f74ea41faed5.jpeg",
        "cafe_nocturno":    "https://d3u0tzju9qaucj.cloudfront.net/e88f2015-c160-4b7e-b0bd-77bca1c4a52a/3949b234-979c-442f-9d61-c6843ad0731a.jpeg",
        "retrato_cercano":  "https://d3u0tzju9qaucj.cloudfront.net/e88f2015-c160-4b7e-b0bd-77bca1c4a52a/c5d8136f-9267-47e8-8a69-a13e42559adb.jpeg",
    }
    url = existing_images.get(scene_key, existing_images["retrato_cercano"])
    return {
        "success": True,
        "url": url,
        "request_id": "fallback",
        "scene": scene_key,
        "mood": SCENE_VARIANTS.get(scene_key, {}).get("mood", ""),
        "is_fallback": True,
    }


def download_image(url: str, dest_path: Path) -> bool:
    """Descarga la imagen generada al disco local."""
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        print(f"   ⚠️ No se pudo descargar la imagen: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# GENERACIÓN DE CAPTION — Voz de Coraline
# ─────────────────────────────────────────────────────────────────────────────

CORALINE_SYSTEM_PROMPT = """Sos el motor de contenido de CORALINE JONES, una persona editorial digital sofisticada especializada en finanzas, legal y real estate en Argentina y América Latina.

IDENTIDAD:
- Nombre: Coraline Jones
- Tagline: "Coraline observa donde otros improvisan."
- Nicho: Legal · Finanzas · Real estate · Patrimonio · Riesgo · Decisiones inteligentes
- Tono: inteligente, sobrio, observador, selectivo, elegante — directo sin ser agresivo

REGLAS DE VOZ:
- Siempre voseo rioplatense: "vos sabés", "tenés que", "hacés", "mirá", "entendés"
- Nunca lenguaje motivacional (no "transformá tu vida", no "creé en vos mismo")
- Nunca prometer rendimientos ni resultados específicos
- Nunca afirmar credenciales profesionales que no tiene
- Vocabulario clave: criterio · estructura · patrimonio · cláusula · riesgo · liquidez · valor real · decisiones · consecuencia

CONEXIÓN NEWS → CORALINE:
Coraline toma noticias globales y las conecta con su nicho editorial:
- Conflictos armados → impacto en mercados, activos de refugio, contratos en zonas de riesgo
- Crisis económicas → protección patrimonial, dolarización de activos, liquidez
- Geopolítica → reordenamiento de carteras, riesgo país, cómo leer el contexto macro
- Salud global → valuación de activos en incertidumbre, seguros, contratos de largo plazo
- Cambios institucionales → qué significa para las reglas del juego legales y financieras

FORMATO DEL CAPTION (Instagram/TikTok):
- 3 a 7 líneas de texto corrido
- Apertura: observación concreta sobre la noticia, sin decir "Coraline dice" — ella ES quien habla
- Desarrollo: qué significa esto desde la perspectiva del patrimonio/riesgo/contratos
- Cierre: reflexión o pregunta sutil — sin CTA agresivo
- NO usar "link en bio", no usar emojis en exceso (máximo 2-3 selectivos)
- SÍ usar saltos de línea para ritmo
- Después del caption: 25 hashtags relevantes (mix español/inglés)
- El caption NUNCA menciona que es IA, nunca menciona "Coraline Jones" en tercera persona"""


def generate_caption_claude(news_headline: str, news_summary: str, news_category: str, rank: int) -> dict:
    """
    Genera el caption de Coraline para una noticia usando Claude API.
    Retorna dict con caption, hashtags y hook.
    """
    if not ANTHROPIC_API_KEY:
        print("   ⚠️ Sin ANTHROPIC_API_KEY — generando caption sin Claude")
        return _generate_caption_template(news_headline, news_summary, news_category)

    try:
        import anthropic as ant
        client = ant.Anthropic(api_key=ANTHROPIC_API_KEY)

        user_prompt = f"""Generá un caption de Instagram para CORALINE JONES basado en esta noticia global.

NOTICIA #{rank}:
Categoría: {news_category}
Titular: {news_headline}
Resumen: {news_summary[:400]}

La noticia es un hecho del mundo real. Coraline la observa desde su perspectiva editorial:
¿qué significa para el patrimonio, el riesgo, los contratos o las decisiones financieras?

No explicar la noticia completa — tomarla como punto de partida para un insight de Coraline.

Devolvé un JSON con:
{{
  "caption": "<el caption en español con voseo, 4-6 líneas, sin hashtags aquí>",
  "hashtags": "<25 hashtags relevantes separados por espacio>",
  "hook": "<primeras 5-7 palabras, el gancho para thumbnail>"
}}

Solo JSON, sin markdown."""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=CORALINE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw = response.content[0].text.strip()
        # Limpiar posible markdown
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        return {
            "success": True,
            "caption": data.get("caption", ""),
            "hashtags": data.get("hashtags", ""),
            "hook": data.get("hook", ""),
            "generated_by": "claude",
        }

    except Exception as e:
        print(f"   ⚠️ Error generando caption con Claude: {e}")
        return _generate_caption_template(news_headline, news_summary, news_category)


def _generate_caption_template(headline: str, summary: str, category: str) -> dict:
    """
    Fallback: genera un caption básico sin Claude.
    Útil para testing sin API key.
    """
    category_connections = {
        "CONFLICTO": "Cuando hay conflicto armado en el mundo, los mercados de activos de refugio se mueven primero. El oro, los bonos cortos, las divisas fuertes. Entender el contexto geopolítico es parte del criterio patrimonial.",
        "ECONOMÍA GLOBAL": "Los mercados globales no esperan. Cuando una economía grande se mueve, el efecto llega — aunque no siempre donde se espera. La pregunta no es si te va a afectar, sino cuándo y en qué.",
        "GEOPOLÍTICA": "El mapa geopolítico no es solo noticias. Es el contexto donde se valuán los activos, se firman los contratos y se toman las decisiones más grandes. Coraline observa lo que el ruido mediático no explica.",
        "SALUD GLOBAL": "En momentos de incertidumbre global, las decisiones mal documentadas cuestan más. Los contratos de largo plazo, las coberturas de seguros, la liquidez disponible — todo vuelve a importar.",
        "HUMANITARIO": "Detrás de cada crisis humanitaria hay consecuencias económicas que los análisis superficiales no alcanzan a ver. Coraline observa la capa que está debajo del titular.",
    }

    connection = category_connections.get(
        category,
        "El mundo se mueve. Y cada movimiento tiene consecuencias sobre activos, contratos y decisiones. Observar con criterio es el primer paso."
    )

    caption = f"Mirá lo que está pasando hoy en el mundo.\n\n{connection}\n\nLa información no alcanza si no sabés qué buscar en ella."
    hashtags = "#patrimonio #criterio #finanzas #legal #realestate #decisiones #riesgo #contratos #inversion #argentina #economia #mercados #geopolitica #macroeconomia #actualidad #coraline #estrategia #proteccionpatrimonial #liquidez #activosreales #valorrreal #decisiones #capitalinteligente #finanzaspersonales #educacionfinanciera"

    return {
        "success": True,
        "caption": caption,
        "hashtags": hashtags,
        "hook": "Mirá lo que está pasando",
        "generated_by": "template",
    }


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE PRINCIPAL — Genera los 2 posts
# ─────────────────────────────────────────────────────────────────────────────

def generate_posts(top5: list, output_dir: str = "output") -> list[dict]:
    """
    Genera 2 posts completos de Coraline (imagen + caption) para las noticias #1 y #2.

    top5: lista de (cluster, breakdown) del scorer
    output_dir: carpeta donde guardar los posts

    Retorna lista de dicts con toda la información del post.
    """
    from formatter import _get_category_label, _summarize_cluster, _get_source_list

    if not top5:
        print("❌ No hay noticias en el top para generar posts de Coraline")
        return []

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    posts_dir = Path(output_dir) / "coraline_posts" / date_str
    posts_dir.mkdir(parents=True, exist_ok=True)

    posts = []
    used_scenes = set()

    for rank_idx in range(min(2, len(top5))):
        cluster, breakdown = top5[rank_idx]
        rank = rank_idx + 1

        rep = cluster.representative_article
        tags = rep.tags if rep else []
        text = cluster.event_label + " " + (rep.summary if rep else "")

        category = _get_category_label(tags, text)
        summary = _summarize_cluster(cluster, max_words=80)
        sources = _get_source_list(cluster, max_sources=4)

        print(f"\n{'='*60}")
        print(f"📰 POST #{rank} — {category}: {cluster.event_label[:55]}...")
        print(f"{'='*60}")

        # ─── 1. Seleccionar escena ────────────────────────────────────────
        scene = select_scene(category, rank)

        # Evitar usar la misma escena para #1 y #2
        if scene["key"] in used_scenes:
            fallback_scenes = [k for k in SCENE_VARIANTS if k not in used_scenes]
            if fallback_scenes:
                alt_key = fallback_scenes[0]
                scene = {"key": alt_key, **SCENE_VARIANTS[alt_key]}
                print(f"   Escena alternada a [{alt_key}] para evitar repetición")

        used_scenes.add(scene["key"])
        print(f"   Escena seleccionada: {scene['key']} ({scene['mood']})")

        # ─── 2. Generar imagen de Coraline ───────────────────────────────
        print(f"   Generando imagen...")
        aspect = "1:1" if rank == 1 else "9:16"
        image_result = generate_coraline_image(scene, news_context=cluster.event_label, aspect_ratio=aspect)

        # Descargar imagen localmente si se obtuvo URL
        local_image_path = None
        if image_result.get("url"):
            filename = f"coraline_news_{rank}_{scene['key']}_{date_str}.jpg"
            local_path = posts_dir / filename
            if download_image(image_result["url"], local_path):
                local_image_path = str(local_path)
                print(f"   ✅ Imagen guardada: {filename}")

        # ─── 3. Generar caption ───────────────────────────────────────────
        print(f"   Generando caption en voz de Coraline...")
        caption_result = generate_caption_claude(
            news_headline=cluster.event_label,
            news_summary=summary,
            news_category=category,
            rank=rank,
        )
        print(f"   ✅ Caption generado ({caption_result.get('generated_by', '?')})")

        # ─── 4. Armar paquete del post ────────────────────────────────────
        post = {
            "rank": rank,
            "date": date_str,
            "status": "pendiente_revision_humana",

            # Noticia fuente
            "news": {
                "headline": cluster.event_label,
                "category": category,
                "summary": summary,
                "score": breakdown.total_score,
                "sources": sources,
                "url": rep.url if rep else None,
            },

            # Imagen de Coraline
            "image": {
                "url": image_result.get("url"),
                "local_path": local_image_path,
                "scene": scene["key"],
                "mood": scene["mood"],
                "aspect_ratio": aspect,
                "is_fallback": image_result.get("is_fallback", False),
                "request_id": image_result.get("request_id"),
            },

            # Caption de Coraline
            "caption": {
                "text": caption_result.get("caption", ""),
                "hashtags": caption_result.get("hashtags", ""),
                "hook": caption_result.get("hook", ""),
                "full_post": f"{caption_result.get('caption', '')}\n\n{caption_result.get('hashtags', '')}",
                "generated_by": caption_result.get("generated_by", ""),
            },

            # Plataformas target
            "platforms": ["instagram", "tiktok"],
            "review_required": True,
            "notes": f"Generado automáticamente a partir de la noticia #{rank} del día. REQUIERE REVISIÓN ANTES DE PUBLICAR.",
        }

        posts.append(post)
        _print_post_preview(post)

    # Guardar el paquete completo en JSON
    output_file = posts_dir / f"coraline_posts_{date_str}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    print(f"\n📦 Paquete de posts guardado: {output_file}")

    # También guardar en el formato de posts_queue del pipeline de Coraline
    _append_to_pipeline_queue(posts)

    return posts


def _print_post_preview(post: dict):
    """Imprime un preview del post generado."""
    print(f"\n{'─'*60}")
    print(f"✅ POST #{post['rank']} LISTO PARA REVISIÓN")
    print(f"{'─'*60}")
    print(f"📰 Noticia: {post['news']['headline'][:65]}")
    print(f"🎨 Imagen:  Escena '{post['image']['scene']}' | {post['image']['aspect_ratio']}")
    print(f"           {'⚠️ FALLBACK (imagen existente)' if post['image']['is_fallback'] else '✨ NUEVA imagen generada'}")
    if post['image']['url']:
        print(f"           URL: {post['image']['url'][:60]}...")
    print(f"\n📝 CAPTION CORALINE:")
    for line in post['caption']['text'].split('\n'):
        print(f"   {line}")
    print(f"\n🏷️  Hashtags: {post['caption']['hashtags'][:80]}...")
    print(f"\n⚠️  {post['notes']}")


def _append_to_pipeline_queue(posts: list):
    """
    Agrega los posts generados a la cola del pipeline de Coraline
    para que aparezcan en el flujo de revisión existente.
    """
    queue_file = CORALINE_PIPELINE_DIR / "content" / "posts_queue.json"

    try:
        existing = []
        if queue_file.exists():
            with open(queue_file, "r", encoding="utf-8") as f:
                existing = json.load(f)

        for post in posts:
            queue_entry = {
                "id": f"news_{post['date']}_{post['rank']}",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source": "global_news_agent",
                "status": "pending_review",
                "caption": post["caption"]["full_post"],
                "image_url": post["image"]["url"],
                "image_scene": post["image"]["scene"],
                "news_headline": post["news"]["headline"],
                "news_category": post["news"]["category"],
                "news_score": post["news"]["score"],
                "platforms": post["platforms"],
            }
            existing.append(queue_entry)

        with open(queue_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        print(f"   ✅ Posts agregados a la cola del pipeline de Coraline ({queue_file.name})")

    except Exception as e:
        print(f"   ⚠️ No se pudo agregar a la cola: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# PUNTO DE ENTRADA INDEPENDIENTE
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Test del módulo con datos sintéticos (sin necesidad de correr el news agent completo).
    """
    print("🧪 TEST del módulo Coraline News — datos sintéticos\n")

    # Simular top5 simplificado para test
    class FakeArticle:
        title = "Iran war: US troops wounded in missile strike on Saudi base"
        summary = "Iranian-backed forces launched a missile and drone attack on Prince Sultan Air Base in Saudi Arabia, wounding at least 15 US soldiers. Markets reacted with oil prices rising 4%. The incident escalates regional tensions as both sides signal continued military operations."
        url = "https://www.aljazeera.com/news/2026/3/28/iran-strike-saudi"
        source_name = "Al Jazeera"
        source_region = "middle_east_north_africa"
        source_tier = 1
        tags = ["conflict", "middle_east", "geopolitics", "energy"]
        language = "en"
        published_at = datetime.now(timezone.utc)

    class FakeCluster:
        cluster_id = "test_001"
        event_label = "Iran war: US troops wounded in missile strike on Saudi base"
        articles = [FakeArticle()]
        article_count = 4
        unique_sources = 3
        unique_regions = 2
        regions = ["middle_east_north_africa", "americas"]
        representative_article = FakeArticle()
        first_seen = datetime.now(timezone.utc)
        days_active = 1
        is_noise = False

    class FakeBreakdown:
        total_score = 74.5
        geopolitical_impact = 10.0
        economic_impact = 7.0
        severity_urgency = 8.0
        geographic_reach = 6.0
        source_diversity = 3.0
        topic_persistence = 5.0
        institutional_rel = 2.0
        boosts_applied = ["armed_conflict_active (+15)"]
        boost_total = 15.0
        regional_penalty = 0
        why_top5 = "Cubierto por 3 medios en 2 regiones. Alto impacto geopolítico."
        rank = 1

    top5_fake = [(FakeCluster(), FakeBreakdown())]

    posts = generate_posts(top5_fake, output_dir="output")
    print(f"\n✅ Test completado — {len(posts)} post(s) generados")
