"""
formatter.py — Output del ranking en múltiples formatos.

Formatos soportados:
1. JSON — estructurado, con score breakdown completo
2. WhatsApp — texto formateado con emojis y markdown básico
3. Email — HTML formateado para clientes de correo
4. Markdown — para GitHub, Obsidian, reportes

Principio: el output debe ser legible sin necesidad de software adicional.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# EMOJIS POR CATEGORÍA TEMÁTICA
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_EMOJIS = {
    "conflict": "⚔️",
    "war": "💣",
    "nuclear": "☢️",
    "economy": "📉",
    "markets": "📊",
    "health": "🏥",
    "pandemic": "🦠",
    "environment": "🌍",
    "climate": "🌡️",
    "energy": "⚡",
    "geopolitics": "🌐",
    "institutional": "🏛️",
    "humanitarian": "🆘",
    "election": "🗳️",
    "diplomacy": "🤝",
    "sanctions": "🚫",
    "default": "📰",
}

RANK_EMOJIS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

SCORE_LABELS = {
    (90, 100): "CRÍTICO",
    (75, 90): "MUY ALTO",
    (60, 75): "ALTO",
    (45, 60): "MODERADO",
    (0, 45): "BAJO",
}


def _get_score_label(score: float) -> str:
    for (low, high), label in SCORE_LABELS.items():
        if low <= score < high:
            return label
    return "BAJO"


def _get_category_emoji(tags: list, text: str) -> str:
    text_lower = text.lower()
    for tag in tags:
        if tag in CATEGORY_EMOJIS:
            return CATEGORY_EMOJIS[tag]
    for keyword, emoji in CATEGORY_EMOJIS.items():
        if keyword in text_lower:
            return emoji
    return CATEGORY_EMOJIS["default"]


def _get_category_label(tags: list, text: str) -> str:
    text_lower = text.lower()
    category_map = {
        "conflict": "CONFLICTO",
        "war": "GUERRA",
        "nuclear": "NUCLEAR",
        "economy": "ECONOMÍA GLOBAL",
        "markets": "MERCADOS",
        "health": "SALUD GLOBAL",
        "pandemic": "PANDEMIA",
        "environment": "MEDIO AMBIENTE",
        "energy": "ENERGÍA",
        "geopolitics": "GEOPOLÍTICA",
        "institutional": "INSTITUCIONES",
        "humanitarian": "HUMANITARIO",
        "election": "ELECCIONES",
        "diplomacy": "DIPLOMACIA",
        "sanctions": "SANCIONES",
    }
    for key, label in category_map.items():
        if key in tags or key in text_lower:
            return label
    return "INTERNACIONAL"


def _summarize_cluster(cluster, max_words: int = 120) -> str:
    """
    Genera un resumen rico del evento usando todo el texto disponible.
    Prioriza: full_text > summary RSS limpio > títulos del cluster.
    """
    rep = cluster.representative_article
    if not rep:
        return cluster.event_label

    # Intentar con full_text primero (si fue scrapeado)
    text = ""
    if hasattr(rep, "full_text") and rep.full_text and len(rep.full_text.split()) > 50:
        text = rep.full_text
    elif rep.summary and len(rep.summary.split()) > 15:
        text = rep.summary

    # Si el texto empieza con el título (común en RSS), eliminarlo
    title_clean = cluster.event_label.strip().rstrip(".")
    if text.startswith(title_clean):
        text = text[len(title_clean):].lstrip(" .,\n")
    elif len(title_clean) > 20:
        # Comparar palabras clave (las primeras 5 del título)
        title_words = set(cluster.event_label.lower().split()[:5])
        first_words = set(text.lower().split()[:5])
        if len(title_words & first_words) >= 4:
            # Saltar hasta el primer punto
            dot_pos = text.find(". ")
            if dot_pos > 0 and dot_pos < 200:
                text = text[dot_pos + 2:]

    if not text.strip():
        # Fallback: concatenar títulos de artículos del cluster
        titles = list(dict.fromkeys(a.title for a in cluster.articles[:5]))
        return " | ".join(titles[:3])

    words = text.split()
    if len(words) > max_words:
        # Cortar en la última oración completa antes del límite
        truncated = " ".join(words[:max_words])
        last_period = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
        if last_period > len(truncated) // 2:
            return truncated[:last_period + 1]
        return truncated + "..."

    return text.strip()


def _get_source_list(cluster, max_sources: int = 5) -> list[str]:
    """Retorna lista de fuentes únicas del cluster."""
    seen = set()
    sources = []
    for article in cluster.articles:
        name = article.source_name
        if name not in seen:
            seen.add(name)
            sources.append(name)
        if len(sources) >= max_sources:
            break
    return sources


# ─────────────────────────────────────────────────────────────────────────────
# FORMATO 1: JSON ESTRUCTURADO
# ─────────────────────────────────────────────────────────────────────────────

def format_json(
    top5: list,
    date: str = None,
    total_articles_ingested: int = 0,
    total_clusters: int = 0,
) -> dict:
    """
    Genera el output JSON completo con toda la metadata del pipeline.

    top5: lista de (cluster, breakdown) del scorer
    """
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    output = {
        "date": date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": "1.0.0",
        "articles_ingested": total_articles_ingested,
        "clusters_identified": total_clusters,
        "top5": [],
    }

    for i, (cluster, breakdown) in enumerate(top5):
        rep = cluster.representative_article
        tags = rep.tags if rep else []
        text = cluster.event_label + " " + (rep.summary if rep else "")

        item = {
            "rank": i + 1,
            "cluster_id": cluster.cluster_id,
            "event": cluster.event_label,
            "category": _get_category_label(tags, text),
            "summary": _summarize_cluster(cluster, max_words=80),
            "score": breakdown.total_score,
            "score_label": _get_score_label(breakdown.total_score),
            "score_breakdown": breakdown.to_dict(),
            "why_top5": breakdown.why_top5,
            "article_count": cluster.article_count,
            "sources": _get_source_list(cluster, max_sources=8),
            "unique_sources": cluster.unique_sources,
            "regions_covered": cluster.regions,
            "first_seen": cluster.first_seen.isoformat() if cluster.first_seen else None,
            "days_active": cluster.days_active,
            "url_principal": rep.url if rep else None,
            "language": rep.language if rep else "en",
        }
        output["top5"].append(item)

    return output


def save_json(output: dict, output_dir: str = "output") -> str:
    """Guarda el JSON en disco y retorna el path."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{output['date']}.json"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    return filepath


# ─────────────────────────────────────────────────────────────────────────────
# FORMATO 2: WHATSAPP / TELEGRAM
# ─────────────────────────────────────────────────────────────────────────────

def _build_why_top5(cluster, breakdown) -> list[str]:
    """Genera 3 razones editoriales por las que la noticia entra en el Top 5."""
    reasons = []

    # Razón 1: cobertura multi-fuente / multi-región
    if cluster.unique_sources >= 4:
        reasons.append(f"Cubierta por {cluster.unique_sources} medios independientes en {cluster.unique_regions} regiones distintas")
    elif cluster.unique_sources >= 2:
        reasons.append(f"Confirmada por {cluster.unique_sources} fuentes en {cluster.unique_regions} región(es)")
    else:
        reasons.append("Fuente de alto tier con señal geopolítica clara")

    # Razón 2: dimensión dominante
    dims = {
        "impacto geopolítico directo": breakdown.geopolitical_impact,
        "impacto económico global": breakdown.economic_impact,
        "severidad y urgencia": breakdown.severity_urgency,
        "alcance geográfico amplio": breakdown.geographic_reach,
        "relevancia institucional": breakdown.institutional_rel,
    }
    top_dim = max(dims, key=dims.get)
    top_val = dims[top_dim]
    if top_val > 0:
        reasons.append(f"Alto {top_dim} ({top_val:.0f}/10)")

    # Razón 3: boosts o persistencia
    if breakdown.boosts_applied:
        boost_name = breakdown.boosts_applied[0].split(" (+")[0].replace("_", " ")
        reasons.append(f"Activó alerta crítica: {boost_name}")
    elif breakdown.topic_persistence > 5:
        reasons.append("Evento en desarrollo con múltiples días de cobertura activa")
    elif breakdown.total_score >= 60:
        reasons.append("Score editorial alto en múltiples dimensiones de impacto global")
    else:
        reasons.append("Mejor candidato disponible en su macrotema para equilibrar el ranking")

    return reasons[:3]


def format_whatsapp(top5: list, date: str = None, excluded: list = None) -> str:
    """
    Genera texto formateado para WhatsApp/iMessage con el nuevo formato editorial rico.
    Cada noticia incluye resumen (90-140 palabras), razones de inclusión,
    región, tema, score y cluster.
    Al final: eventos que quedaron fuera + chequeo de equilibrio.
    """
    if date is None:
        date = datetime.now(timezone.utc).strftime("%d %b %Y")

    lines = []

    # Header
    lines.append(f"🌍 *TOP 5 NOTICIAS GLOBALES — {date}*")
    lines.append("_Importancia real, no viralidad. Sin duplicados de evento._")
    lines.append("")

    for i, (cluster, breakdown) in enumerate(top5):
        rep = cluster.representative_article
        rank_num = i + 1
        rank_emoji = RANK_EMOJIS[i] if i < len(RANK_EMOJIS) else f"{i+1}."

        # Título
        lines.append(f"━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"{rank_emoji} *#{rank_num} — {cluster.event_label}*")
        lines.append("")

        # Resumen de 90-140 palabras
        summary = _summarize_cluster(cluster, max_words=140)
        lines.append(f"*Resumen:*")
        lines.append(summary)
        lines.append("")

        # Por qué entra en el Top 5
        reasons = _build_why_top5(cluster, breakdown)
        lines.append(f"*Por qué entra en el Top 5:*")
        for r in reasons:
            lines.append(f"• {r}")
        lines.append("")

        # Metadata
        tema = getattr(breakdown, "macrotema", "") or _get_category_label(rep.tags if rep else [], cluster.event_label)
        region_label = getattr(breakdown, "broad_region", "") or (
            ", ".join(cluster.regions[:2]) if cluster.regions else "global"
        )
        sources_list = _get_source_list(cluster, max_sources=4)
        sources_str = " · ".join(sources_list) if sources_list else "múltiples fuentes"

        lines.append(f"📍 Región: {region_label}  |  🏷 Tema: {tema}")
        lines.append(f"📰 {sources_str}")
        lines.append(f"📊 Score: {breakdown.total_score:.0f}/100  |  Cluster: {cluster.event_label[:40]}")

        # Boosts críticos
        if breakdown.boosts_applied:
            boost_reasons = [b.split(" (+")[0].replace("_", " ").title() for b in breakdown.boosts_applied[:2]]
            lines.append(f"⚠️ _Alerta: {', '.join(boost_reasons)}_")

        # Link
        if rep and rep.url:
            lines.append(f"🔗 {rep.url}")

        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    # Bloque A: Eventos que quedaron fuera
    lines.append("")
    lines.append("*📋 Eventos importantes que quedaron fuera:*")
    excluded_shown = (excluded or [])[:5]
    if excluded_shown:
        for cluster, breakdown, *_ in excluded_shown:
            tema = getattr(breakdown, "macrotema", "")
            motivo = "duplicado temático" if tema else "update menor o impacto más local"
            # Intentar inferir motivo real
            if hasattr(breakdown, "macrotema") and breakdown.macrotema:
                motivo = f"duplicado temático ({breakdown.macrotema})"
            lines.append(f"• {cluster.event_label[:60]}… — _{motivo}_")
    else:
        lines.append("• (no hay suficientes eventos adicionales para listar)")
    lines.append("")

    # Bloque B: Chequeo de equilibrio
    lines.append("*⚖️ Chequeo de equilibrio del ranking:*")
    macrotemas_en = {}
    regiones_en = {}
    for cluster, breakdown in top5:
        t = getattr(breakdown, "macrotema", "sin clasificar")
        r = getattr(breakdown, "broad_region", "global")
        macrotemas_en[t] = macrotemas_en.get(t, 0) + 1
        regiones_en[r] = regiones_en.get(r, 0) + 1

    lines.append(f"• Regiones representadas: {len(regiones_en)} ({', '.join(regiones_en.keys())})")
    lines.append(f"• Temas representados: {len(macrotemas_en)} ({', '.join(macrotemas_en.keys())})")

    concentracion = [f"{t} x{c}" for t, c in macrotemas_en.items() if c > 1]
    if concentracion:
        lines.append(f"• Concentración: {', '.join(concentracion)}")
    else:
        lines.append("• Sin concentración excesiva en ningún tema")

    dup_check = "✅ Sin duplicados de evento detectados" if len(top5) == len(set(id(c) for c, _ in top5)) else "⚠️ Revisar posibles duplicados"
    lines.append(f"• {dup_check}")
    lines.append("")

    # Footer
    lines.append(f"🤖 _Procesado automáticamente — {date}_")

    return "\n".join(lines)


def save_whatsapp(text: str, output_dir: str = "output", date: str = None) -> str:
    """Guarda el texto WhatsApp en disco."""
    os.makedirs(output_dir, exist_ok=True)
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{date}_whatsapp.txt"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)
    return filepath


# ─────────────────────────────────────────────────────────────────────────────
# FORMATO 3: EMAIL HTML
# ─────────────────────────────────────────────────────────────────────────────

def format_email_html(top5: list, date: str = None) -> str:
    """
    Genera HTML para email con diseño limpio y profesional.
    Compatible con Gmail, Outlook, Apple Mail.
    """
    if date is None:
        date = datetime.now(timezone.utc).strftime("%d de %B de %Y")

    items_html = []

    for i, (cluster, breakdown) in enumerate(top5):
        rep = cluster.representative_article
        tags = rep.tags if rep else []
        text = cluster.event_label + " " + (rep.summary if rep else "")

        emoji = _get_category_emoji(tags, text)
        category = _get_category_label(tags, text)
        rank_emoji = RANK_EMOJIS[i] if i < len(RANK_EMOJIS) else f"#{i+1}"
        summary = _summarize_cluster(cluster, max_words=60)
        sources = _get_source_list(cluster, max_sources=5)
        score_color = "#c0392b" if breakdown.total_score >= 80 else "#e67e22" if breakdown.total_score >= 60 else "#27ae60"
        url = rep.url if rep else "#"

        item_html = f"""
        <div style="border-left: 4px solid {score_color}; padding: 15px; margin: 20px 0; background: #f9f9f9; border-radius: 4px;">
          <div style="font-size:11px; color:#888; text-transform:uppercase; letter-spacing:1px; margin-bottom:5px;">
            {rank_emoji} {emoji} {category}
          </div>
          <h2 style="font-size:18px; color:#1a1a1a; margin: 0 0 8px 0; line-height:1.4;">
            <a href="{url}" style="color:#1a1a1a; text-decoration:none;">{cluster.event_label}</a>
          </h2>
          <p style="color:#444; font-size:14px; line-height:1.6; margin: 0 0 12px 0;">{summary}</p>
          <div style="font-size:12px; color:#666;">
            <span style="background:{score_color}; color:white; padding:2px 8px; border-radius:3px; font-weight:bold;">
              Score {breakdown.total_score:.0f}/100
            </span>
            &nbsp;&nbsp;
            {cluster.unique_sources} fuentes · {cluster.unique_regions} región(es)
          </div>
          <div style="margin-top:10px; font-size:12px; color:#888;">
            📰 {' · '.join(sources)}
          </div>
        </div>
        """
        items_html.append(item_html)

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: Georgia, 'Times New Roman', serif; max-width:680px; margin:0 auto; padding:20px; background:#fff;">
  <div style="border-bottom: 2px solid #1a1a1a; padding-bottom:15px; margin-bottom:20px;">
    <h1 style="font-size:24px; color:#1a1a1a; margin:0;">🌍 Top 5 Noticias Globales</h1>
    <p style="color:#888; font-size:13px; margin:5px 0 0 0;">{date} · Sistema editorial autónomo · No por viralidad, sino por importancia</p>
  </div>

  {"".join(items_html)}

  <div style="border-top:1px solid #ddd; margin-top:30px; padding-top:15px; font-size:11px; color:#aaa; text-align:center;">
    Sistema Global News Agent · Anti-sesgo regional activo · Fuentes diversificadas en 6 regiones<br>
    Criterios: impacto geopolítico, económico, alcance geográfico, severidad, diversidad de fuentes
  </div>
</body>
</html>"""

    return html


def save_email_html(html: str, output_dir: str = "output", date: str = None) -> str:
    """Guarda el HTML de email en disco."""
    os.makedirs(output_dir, exist_ok=True)
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{date}_email.html"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    return filepath


# ─────────────────────────────────────────────────────────────────────────────
# FORMATO 4: MARKDOWN
# ─────────────────────────────────────────────────────────────────────────────

def format_markdown(top5: list, output_dict: dict) -> str:
    """Genera Markdown para GitHub, Obsidian o reportes."""
    date = output_dict.get("date", datetime.now().strftime("%Y-%m-%d"))

    lines = [
        f"# 🌍 Top 5 Noticias Globales — {date}",
        "",
        f"> Sistema editorial autónomo | {output_dict.get('articles_ingested', '?')} artículos procesados → {output_dict.get('clusters_identified', '?')} eventos → top 5",
        "",
        "---",
        "",
    ]

    for i, (cluster, breakdown) in enumerate(top5):
        rep = cluster.representative_article
        tags = rep.tags if rep else []
        text = cluster.event_label + " " + (rep.summary if rep else "")
        category = _get_category_label(tags, text)
        summary = _summarize_cluster(cluster, max_words=70)
        sources = _get_source_list(cluster, max_sources=6)
        rank_emoji = RANK_EMOJIS[i] if i < len(RANK_EMOJIS) else f"#{i+1}"
        url = rep.url if rep else "#"

        lines += [
            f"## {rank_emoji} [{category}] {cluster.event_label}",
            "",
            f"**Score:** `{breakdown.total_score:.1f}/100` | "
            f"**Fuentes:** {cluster.unique_sources} | "
            f"**Regiones:** {cluster.unique_regions}",
            "",
            summary,
            "",
            f"**Fuentes consultadas:** {', '.join(sources)}",
            "",
            f"**¿Por qué importa?** {breakdown.why_top5}",
            "",
        ]

        # Score breakdown table
        lines += [
            "| Dimensión | Score (0-10) | Peso | Contribución |",
            "|---|---|---|---|",
            f"| Impacto geopolítico | {breakdown.geopolitical_impact:.1f} | 25% | {breakdown.geopolitical_impact * 2.5:.1f} |",
            f"| Impacto económico | {breakdown.economic_impact:.1f} | 20% | {breakdown.economic_impact * 2.0:.1f} |",
            f"| Alcance geográfico | {breakdown.geographic_reach:.1f} | 15% | {breakdown.geographic_reach * 1.5:.1f} |",
            f"| Severidad/Urgencia | {breakdown.severity_urgency:.1f} | 15% | {breakdown.severity_urgency * 1.5:.1f} |",
            f"| Diversidad de fuentes | {breakdown.source_diversity:.1f} | 10% | {breakdown.source_diversity * 1.0:.1f} |",
            f"| Persistencia del tema | {breakdown.topic_persistence:.1f} | 10% | {breakdown.topic_persistence * 1.0:.1f} |",
            f"| Relevancia institucional | {breakdown.institutional_rel:.1f} | 5% | {breakdown.institutional_rel * 0.5:.1f} |",
        ]

        if breakdown.boosts_applied:
            lines.append("")
            lines.append(f"**Boosts aplicados:** {', '.join(breakdown.boosts_applied)}")

        lines += ["", f"🔗 [Leer artículo principal]({url})", "", "---", ""]

    lines += [
        "",
        "*Generado por Global News Agent · Criterio editorial, no algoritmo de popularidad*",
    ]

    return "\n".join(lines)


def save_markdown(text: str, output_dir: str = "output", date: str = None) -> str:
    """Guarda el Markdown en disco."""
    os.makedirs(output_dir, exist_ok=True)
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{date}_report.md"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)
    return filepath


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN PRINCIPAL — GUARDAR TODOS LOS FORMATOS
# ─────────────────────────────────────────────────────────────────────────────

def save_all_formats(
    top5: list,
    output_dir: str = "output",
    total_articles: int = 0,
    total_clusters: int = 0,
    excluded: list = None,
) -> dict[str, str]:
    """
    Genera y guarda todos los formatos de output.
    Retorna dict con paths de los archivos generados.
    """
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_display = datetime.now(timezone.utc).strftime("%d %b %Y")

    # JSON
    json_data = format_json(top5, date=date, total_articles_ingested=total_articles, total_clusters=total_clusters)
    json_path = save_json(json_data, output_dir)

    # WhatsApp
    wa_text = format_whatsapp(top5, date=date_display, excluded=excluded)
    wa_path = save_whatsapp(wa_text, output_dir, date=date)

    # Email HTML
    email_html = format_email_html(top5, date=date_display)
    email_path = save_email_html(email_html, output_dir, date=date)

    # Markdown
    md_text = format_markdown(top5, json_data)
    md_path = save_markdown(md_text, output_dir, date=date)

    paths = {
        "json": json_path,
        "whatsapp": wa_path,
        "email_html": email_path,
        "markdown": md_path,
    }

    return paths, wa_text  # Retorna también el texto WhatsApp para impresión en consola
