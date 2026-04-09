# kworb_scraper

A Python project to scrape music chart data from [kworb.net](https://kworb.net) and store it in PostgreSQL.

## Features
- Scrapes **iTunes Global Artist Rankings** (top 300)
- Scrapes **Spotify Artists** (monthly listeners, peak data)
- Scrapes **Artist Details** from kworb profile pages (songs, albums, **Latin American countries** snapshot)
- Captures **Trending Artists for Last Month** (stored per calendar month)
- Stores all data in PostgreSQL with full audit trail (`scrape_runs` table)
- Daily scheduler built-in

---

## Project Structure

```
kworb_scraper/
├── config/
│   ├── __init__.py
│   └── settings.py          # Env-based configuration
├── migrations/
│   └── 001_create_tables.sql
├── src/
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py    # psycopg2 connection helper
│   │   ├── migrate.py       # Migration runner
│   │   ├── models.py        # Dataclass models
│   │   └── repository.py    # DB write operations
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── itunes_scraper.py
│   │   ├── spotify_scraper.py
│   │   └── trending_scraper.py
│   └── utils/
│       ├── __init__.py
│       ├── http_client.py   # Requests + retry + polite delay
│       └── logger.py        # Console + file logger
├── logs/                    # Auto-created, daily log files
├── .env.example
├── main.py
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your PostgreSQL credentials
```

### 3. Run database migrations
```bash
python main.py migrate
```

---

## Usage

| Command | Description |
|---------|-------------|
| `python main.py scrape` | Run all scrapers |
| `python main.py scrape itunes` | iTunes global rankings only |
| `python main.py scrape spotify` | Spotify artist stats only |
| `python main.py scrape trending` | Trending artists (last month) only |
| `python main.py scrape details [limit]` | Artist detail snapshots from kworb profile pages |
| `python main.py schedule` | Run daily at 06:00 UTC |
| `python main.py migrate` | Apply DB migrations |

---

## Database Schema

### `artists`
| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | |
| name | VARCHAR(255) | Unique artist name |
| profile_url | TEXT | kworb profile link |

### `itunes_artist_rankings`
| Column | Type | Description |
|--------|------|-------------|
| rank | INTEGER | Chart position |
| rank_change | VARCHAR | '+3', '-1', '=', 'NEW' |
| total_points / itunes_points / spotify_points … | INTEGER | Score breakdown |
| top_country | VARCHAR | Top-charting country |
| scrape_date | DATE | Date of scrape |

### `spotify_artists`
Monthly listeners and peak data per scrape.

### `trending_artists_monthly`
Top artists stored per `YYYY-MM` month, used for last-month trending analysis. Upserted on re-run.

### `scrape_runs`
Audit log of every scrape run with status and row count.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | localhost | PostgreSQL host |
| `DB_PORT` | 5432 | PostgreSQL port |
| `DB_NAME` | kworb_db | Database name |
| `DB_USER` | postgres | DB username |
| `DB_PASSWORD` | *(required)* | DB password |
| `SCRAPE_DELAY_SECONDS` | 2 | Polite delay between requests |
| `ARTIST_DETAILS_LIMIT` | 10 | Number of artist profile pages to include in the standard run |
| `LOG_LEVEL` | INFO | Logging verbosity |


## Dashboard

Run the Streamlit dashboard:
```bash
python3 -m streamlit run streamlit_app.py
```
