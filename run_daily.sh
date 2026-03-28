#!/bin/bash
# run_daily.sh — Script de ejecución diaria del Global News Agent
#
# USO:
#   ./run_daily.sh                  # Ejecución normal
#   ./run_daily.sh --dry-run        # Sin guardar archivos
#   ./run_daily.sh --verbose        # Logs detallados
#
# CRON (ejecutar todos los días a las 6:00 AM UTC):
#   0 6 * * * cd /ruta/al/proyecto && ./run_daily.sh >> logs/cron.log 2>&1
#
# GITHUB ACTIONS: ver comentario al final del archivo

set -e  # Salir si cualquier comando falla

# ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LOG_DIR="$SCRIPT_DIR/logs"
OUTPUT_DIR="$SCRIPT_DIR/output"
DATE=$(date -u +%Y-%m-%d)
TIMESTAMP=$(date -u +%Y-%m-%d_%H-%M-%S)

# Crear directorios si no existen
mkdir -p "$LOG_DIR" "$OUTPUT_DIR"

# ─── VERIFICACIÓN DEL ENTORNO ─────────────────────────────────────────────────
echo "[$TIMESTAMP] Global News Agent iniciando..."
echo "Directorio: $SCRIPT_DIR"
echo "Python: $($PYTHON_BIN --version)"

# Verificar que las dependencias están instaladas
if ! $PYTHON_BIN -c "import feedparser" 2>/dev/null; then
    echo "ERROR: feedparser no instalado. Ejecutar: pip install -r requirements.txt"
    exit 1
fi

# ─── EJECUCIÓN ───────────────────────────────────────────────────────────────
cd "$SCRIPT_DIR"

echo "[$TIMESTAMP] Ejecutando pipeline..."
$PYTHON_BIN news_agent.py "$@" 2>&1 | tee "$LOG_DIR/run_${DATE}.log"
EXIT_CODE=${PIPESTATUS[0]}

if [ $EXIT_CODE -eq 0 ]; then
    echo "[$TIMESTAMP] ✅ Pipeline completado exitosamente"
    echo "Outputs guardados en: $OUTPUT_DIR/"
    ls -la "$OUTPUT_DIR/$DATE"* 2>/dev/null || echo "(No se encontraron archivos de hoy)"
else
    echo "[$TIMESTAMP] ❌ Pipeline falló con código $EXIT_CODE"
    echo "Ver log: $LOG_DIR/run_${DATE}.log"
    exit $EXIT_CODE
fi

# ─── LIMPIEZA DE LOGS ANTIGUOS (>30 días) ────────────────────────────────────
find "$LOG_DIR" -name "run_*.log" -mtime +30 -delete 2>/dev/null || true

echo "[$TIMESTAMP] Finalizado."

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE GITHUB ACTIONS (copiar a .github/workflows/daily.yml):
# ─────────────────────────────────────────────────────────────────────────────
#
# name: Daily News Agent
# on:
#   schedule:
#     - cron: '0 6 * * *'   # 6:00 AM UTC diario
#   workflow_dispatch:       # Permite ejecución manual
#
# jobs:
#   run-agent:
#     runs-on: ubuntu-latest
#     steps:
#       - uses: actions/checkout@v4
#       - uses: actions/setup-python@v5
#         with:
#           python-version: '3.11'
#       - name: Install dependencies
#         run: pip install -r requirements.txt
#       - name: Run Global News Agent
#         run: python news_agent.py
#       - name: Upload output
#         uses: actions/upload-artifact@v4
#         with:
#           name: daily-news-${{ env.date }}
#           path: output/
# ─────────────────────────────────────────────────────────────────────────────
