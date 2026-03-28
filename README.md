# 🌍 Global News Agent

An autonomous editorial pipeline that ingests RSS feeds from 40+ international outlets, clusters articles by event using multilingual semantic embeddings, ranks them by editorial impact, and delivers a **Top 5 daily briefing** via iMessage every morning.

> Built on editorial judgment, not virality. One event = one slot, regardless of how many articles cover it.

---

## How it works

```
RSS feeds (40+ sources) → date filter → semantic dedup → DBSCAN clustering
→ multidimensional scoring → diversity filter → iMessage delivery
```

**1. Ingestion** — Fetches articles from 40+ international outlets (BBC, Al Jazeera, El País, SCMP, NZZ, The Hindu, Folha de S.Paulo, and more). Articles older than 24h are skipped before any HTTP call, keeping the pipeline fast.

**2. Clustering** — Deduplicates near-identical articles using MinHash LSH, then groups remaining articles by event using `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers) + DBSCAN. Works across 100+ languages without translation.

**3. Scoring** — Each event cluster is scored across 7 editorial dimensions:

| Dimension | Weight |
|---|---|
| Geopolitical impact | 25% |
| Economic impact | 20% |
| Geographic reach | 15% |
| Severity / urgency | 15% |
| Source diversity | 10% |
| Topic persistence | 10% |
| Institutional relevance | 5% |

Critical events (wars, financial crises, major disasters) activate score boosts.

**4. Diversity filter** — Greedy selection enforcing max 2 events per macrotema and max 2 per region, covering: geopolitics/war, economy/markets, politics/institutions, technology/AI, climate/health/society.

**5. Output** — Rich iMessage/WhatsApp format with 90–140 word summaries, editorial reasoning per item, excluded events section, and balance audit.

---

## Setup

```bash
git clone https://github.com/Psflores/global-news-agent
cd global-news-agent
pip3 install -r requirements.txt
```

**Run once:**
```bash
python3 news_agent.py
```

**Run and send via iMessage (macOS):**
```bash
# Edit IMESSAGE_RECIPIENT in send_imessage_ranking.py first
python3 send_imessage_ranking.py
```

**Daily automation (macOS LaunchAgent or cron):**
```bash
# Example cron — every day at 7:30 AM
30 7 * * * cd /path/to/global-news-agent && python3 send_imessage_ranking.py
```

---

## Requirements

- Python 3.9+
- macOS (for iMessage delivery via osascript)
- `sentence-transformers`, `scikit-learn`, `feedparser`, `datasketch`, `newspaper4k`

See `requirements.txt` for the full list.

---

## Output formats

Each run saves to `output/`:

- `YYYY-MM-DD_whatsapp.txt` — iMessage/WhatsApp rich text
- `YYYY-MM-DD_email.html` — HTML email
- `YYYY-MM-DD_report.md` — Markdown report
- `YYYY-MM-DD.json` — Machine-readable full output

---

## Architecture

See [`ARQUITECTURA.md`](ARQUITECTURA.md) for a detailed breakdown of each module.

---

## Sources

Covers major outlets across Latin America, Europe, Middle East, Asia, Africa, and global institutions (UN, WHO, Crisis Group, Bellingcat). Full list in [`sources.py`](sources.py).

---

## License

MIT
