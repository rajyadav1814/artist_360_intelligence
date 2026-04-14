# Artist 360 Intelligence

A Python project to scrape music chart data from [kworb.net](https://kworb.net) and store it in PostgreSQL.

## Features
- Scrapes **iTunes Global Artist Rankings** (top 300)
- Scrapes **Spotify Artists** (monthly listeners, peak data)
- Scrapes **Artist Details** from kworb profile pages (songs, albums, **Latin American countries** snapshot)
- Captures **Trending Artists for Last Month** (stored per calendar month)
- Stores all data in PostgreSQL with full audit trail (`scrape_runs` table)
- Daily scheduler built-in

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
| `python3 main.py scrape` | Run all scrapers |
| `python3 main.py scrape itunes` | iTunes global rankings only |
| `python3 main.py scrape spotify` | Spotify artist stats only |
| `python3 main.py scrape trending` | Trending artists (last month) only |
| `python3 main.py scrape details [limit]` | Artist detail snapshots from kworb profile pages |
| `python3 main.py schedule` | Run daily at 06:00 UTC |
| `python3 main.py migrate` | Apply DB migrations |

---

## Dashboard

Run the Streamlit dashboard:
```bash
python3 -m streamlit run streamlit_app.py
```
