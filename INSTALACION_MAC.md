# Guía de Instalación — Mac

## Paso 1: Instalar Python 3 (si no lo tenés)

```bash
# Opción A: via Homebrew (recomendado)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python3

# Opción B: descargar desde python.org
# https://www.python.org/downloads/macos/
```

## Paso 2: Navegar a la carpeta del proyecto

```bash
# Encontrar la carpeta automáticamente:
find ~ -name "news_agent.py" 2>/dev/null

# Luego entrar (ajustá el path):
cd ~/Documents/INFLUENCER/global_news_agent
# o
cd ~/Desktop/INFLUENCER/global_news_agent
```

## Paso 3: Instalar dependencias

```bash
pip3 install feedparser langdetect scikit-learn datasketch numpy newspaper4k
```

## Paso 4: Primer test

```bash
# Demo con datos sintéticos (no requiere internet):
python3 news_agent.py --demo

# Ejecución real:
python3 news_agent.py
```

---

## Opcional: Activar Ladder para bypasear paywalls

Ladder (github.com/everywall/ladder) permite leer artículos detrás de paywalls
(FT, Reuters, Economist, Le Monde, etc.) sin suscripción.

### Opción A: Docker (más fácil)

```bash
# Instalar Docker Desktop: https://www.docker.com/products/docker-desktop/

# Luego correr Ladder:
docker run -d -p 8080:8080 --name ladder ghcr.io/everywall/ladder:latest

# Activar en el agente:
export LADDER_URL=http://localhost:8080
python3 news_agent.py
```

### Opción B: Binario directo (sin Docker)

```bash
# Descargar desde: https://github.com/everywall/ladder/releases
# Ejemplo para Mac M1/M2:
curl -L https://github.com/everywall/ladder/releases/latest/download/ladder_darwin_arm64 -o ladder
chmod +x ladder
./ladder &   # Corre en background

export LADDER_URL=http://localhost:8080
python3 news_agent.py
```

Con Ladder activado, el sistema podrá leer artículos completos de:
- Reuters (feed actualmente bloqueado sin paywall)
- Financial Times
- The Economist
- Le Monde
- AP News
- Y muchos más

---

## Ejecución automática diaria (cron)

```bash
# Editar crontab:
crontab -e

# Agregar esta línea (ejecuta todos los días a las 7 AM Argentina):
0 10 * * * cd /path/a/tu/INFLUENCER/global_news_agent && LADDER_URL=http://localhost:8080 python3 news_agent.py >> logs/cron.log 2>&1
```

---

## Problemas frecuentes

| Error | Solución |
|---|---|
| `command not found: python` | Usar `python3` en lugar de `python` |
| `command not found: pip` | Usar `pip3` en lugar de `pip` |
| `cd: no such file or directory` | Usar `find ~ -name "news_agent.py"` para encontrar la carpeta |
| `No module named 'feedparser'` | Correr `pip3 install feedparser` |
| Top 5 con artículos de pocos medios | Activar Ladder para desbloquear más fuentes |
