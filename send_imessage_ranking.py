#!/usr/bin/env python3
"""
send_imessage_ranking.py — Envía el ranking diario por iMessage vía osascript.

Uso:
  python3 send_imessage_ranking.py                  # Corre pipeline + envía
  python3 send_imessage_ranking.py --only-send       # Solo envía último output
  python3 send_imessage_ranking.py --dry-run         # Imprime sin enviar
"""

import os
import sys
import glob
import subprocess
import argparse
from datetime import datetime, timezone
from pathlib import Path

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = SCRIPT_DIR / "output"

# ⚠️  Completar con tu número o Apple ID (ej: "+5491155551234" o "tu@email.com")
IMESSAGE_RECIPIENT = "pablosebastianflores@gmail.com"

# Máximo de caracteres por mensaje iMessage (0 = sin límite, iMessage acepta textos largos)
MAX_CHUNK_CHARS = 0

# ─── OBTENER RANKING ──────────────────────────────────────────────────────────

def run_pipeline() -> str:
    """Ejecuta el pipeline y retorna la ruta del archivo WhatsApp generado."""
    print("🚀 Ejecutando Global News Agent...")
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "news_agent.py"), "--no-coraline"],
        cwd=str(SCRIPT_DIR),
        capture_output=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Pipeline falló con código {result.returncode}")
    return get_latest_whatsapp_file()


def get_latest_whatsapp_file() -> str:
    """Encuentra el archivo WhatsApp más reciente en output/."""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pattern = str(OUTPUT_DIR / f"{date}_whatsapp.txt")
    files = glob.glob(pattern)
    if not files:
        # Fallback: cualquier archivo wa del día
        files = glob.glob(str(OUTPUT_DIR / "*_whatsapp.txt"))
    if not files:
        raise FileNotFoundError(
            f"No se encontró archivo WhatsApp en {OUTPUT_DIR}. "
            "Ejecutar primero el pipeline."
        )
    return sorted(files)[-1]


def read_ranking(filepath: str) -> str:
    """Lee el contenido del ranking."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read().strip()


# ─── ENVÍO iMESSAGE ──────────────────────────────────────────────────────────

def send_imessage(recipient: str, text: str, dry_run: bool = False) -> None:
    """Envía un mensaje de texto por iMessage usando osascript."""
    if dry_run:
        print("\n" + "─" * 60)
        print(f"[DRY RUN] Destinatario: {recipient}")
        print("─" * 60)
        print(text)
        print("─" * 60)
        return

    # Escapar comillas y caracteres especiales para AppleScript
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')

    applescript = f'''
tell application "Messages"
    set targetService to 1st service whose service type = iMessage
    set targetBuddy to buddy "{recipient}" of targetService
    send "{escaped}" to targetBuddy
end tell
'''
    result = subprocess.run(
        ["osascript", "-e", applescript],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"osascript falló:\n{result.stderr}\n\n"
            "¿Está Messages abierto? ¿El destinatario está en iMessage?"
        )
    print(f"✅ Ranking enviado por iMessage a {recipient}")


def send_in_chunks(recipient: str, text: str, max_chars: int, dry_run: bool) -> None:
    """Divide en chunks si max_chars > 0, y envía cada uno."""
    if max_chars <= 0 or len(text) <= max_chars:
        send_imessage(recipient, text, dry_run=dry_run)
        return

    # División por párrafos (doble salto de línea)
    parts = text.split("\n\n")
    chunk = ""
    chunk_num = 0
    for part in parts:
        candidate = (chunk + "\n\n" + part).strip()
        if len(candidate) <= max_chars:
            chunk = candidate
        else:
            if chunk:
                chunk_num += 1
                print(f"   Enviando parte {chunk_num} ({len(chunk)} chars)...")
                send_imessage(recipient, chunk, dry_run=dry_run)
            chunk = part
    if chunk:
        chunk_num += 1
        print(f"   Enviando parte {chunk_num} ({len(chunk)} chars)...")
        send_imessage(recipient, chunk, dry_run=dry_run)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Envía el ranking diario por iMessage")
    parser.add_argument("--only-send", action="store_true",
                        help="No corre el pipeline, solo envía el último output")
    parser.add_argument("--dry-run", action="store_true",
                        help="Imprime el mensaje sin enviarlo")
    parser.add_argument("--recipient", default=IMESSAGE_RECIPIENT,
                        help=f"Destinatario iMessage (default: {IMESSAGE_RECIPIENT})")
    args = parser.parse_args()

    try:
        if args.only_send:
            wa_file = get_latest_whatsapp_file()
            print(f"📄 Usando archivo: {wa_file}")
        else:
            wa_file = run_pipeline()
            print(f"📄 Output generado: {wa_file}")

        text = read_ranking(wa_file)
        print(f"📝 Ranking listo ({len(text)} caracteres)")

        send_in_chunks(
            recipient=args.recipient,
            text=text,
            max_chars=MAX_CHUNK_CHARS,
            dry_run=args.dry_run,
        )

    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(2)
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(0)


if __name__ == "__main__":
    main()
