"""
kworb_scraper — Main entry point
---------------------------------
Commands:
  python main.py migrate                  — Apply DB migrations
  python main.py scrape                   — Run standard scrapers (iTunes + Spotify + Trending + Artist Details)
  python main.py scrape itunes            — iTunes global rankings only
  python main.py scrape spotify           — Spotify artist stats only
  python main.py scrape trending          — Trending artists (last month) only
  python main.py scrape details [limit] — Artist detail pages from kworb.net (default: all)
  python main.py schedule                 — Run on a daily schedule
"""
import sys
import time

import schedule as sched

from src.database.repository import (
    log_scrape_run,
    save_artist_details,
    save_itunes_rankings,
    save_spotify_artists,
    save_trending_artists,
    save_spotify_daily,
    save_itunes_daily,
    save_youtube_daily,
)
from src.scrapers.artist_details_scraper import scrape_artist_details
from src.scrapers.itunes_scraper import scrape_itunes_global_artists
from src.scrapers.spotify_scraper import scrape_spotify_artists
from src.scrapers.trending_scraper import scrape_trending_artists_last_month
from src.scrapers.daily_scraper import scrape_spotify_daily, scrape_itunes_daily, scrape_youtube_daily
from src.utils.logger import get_logger

logger = get_logger("main")


def run_itunes():
    logger.info("=== Starting iTunes Global Rankings scrape ===")
    try:
        data = scrape_itunes_global_artists()
        rows = save_itunes_rankings(data)
        log_scrape_run("itunes_global", "success", rows)
        logger.info(f"iTunes scrape complete: {rows} rows saved")
    except Exception as exc:
        log_scrape_run("itunes_global", "failed", error=str(exc))
        logger.error(f"iTunes scrape failed: {exc}")


def run_spotify():
    logger.info("=== Starting Spotify Artists scrape ===")
    try:
        data = scrape_spotify_artists()
        rows = save_spotify_artists(data)
        log_scrape_run("spotify_artists", "success", rows)
        logger.info(f"Spotify scrape complete: {rows} rows saved")
    except Exception as exc:
        log_scrape_run("spotify_artists", "failed", error=str(exc))
        logger.error(f"Spotify scrape failed: {exc}")


def run_trending():
    logger.info("=== Starting Trending Artists (last month) scrape ===")
    try:
        data = scrape_trending_artists_last_month()
        rows = save_trending_artists(data)
        log_scrape_run("trending_last_month", "success", rows)
        logger.info(f"Trending scrape complete: {rows} rows saved")
    except Exception as exc:
        log_scrape_run("trending_last_month", "failed", error=str(exc))
        logger.error(f"Trending scrape failed: {exc}")


def run_artist_details(limit: int | None = None):
    logger.info("=== Starting Artist Details scrape ===")
    try:
        data = scrape_artist_details(limit=limit)
        rows = save_artist_details(data)
        log_scrape_run("artist_details", "success", rows)
        logger.info(f"Artist details scrape complete: {rows} profiles saved")
    except Exception as exc:
        log_scrape_run("artist_details", "failed", error=str(exc))
        logger.error(f"Artist details scrape failed: {exc}")


def run_daily_charts():
    logger.info("=== Starting Daily Charts scrape (Spotify, iTunes, YouTube) ===")
    
    # Spotify Daily
    for country in ["global", "us"]:
        try:
            data = scrape_spotify_daily(country=country)
            rows = save_spotify_daily(data)
            log_scrape_run(f"spotify_daily_{country}", "success", rows)
            logger.info(f"Spotify Daily {country} complete: {rows} rows saved")
        except Exception as exc:
            log_scrape_run(f"spotify_daily_{country}", "failed", error=str(exc))
            logger.error(f"Spotify Daily {country} failed: {exc}")

    # iTunes Daily
    for country in ["ww", "us"]:
        try:
            data = scrape_itunes_daily(country=country)
            rows = save_itunes_daily(data)
            log_scrape_run(f"itunes_daily_{country}", "success", rows)
            logger.info(f"iTunes Daily {country} complete: {rows} rows saved")
        except Exception as exc:
            log_scrape_run(f"itunes_daily_{country}", "failed", error=str(exc))
            logger.error(f"iTunes Daily {country} failed: {exc}")

    # YouTube Daily
    try:
        data = scrape_youtube_daily()
        rows = save_youtube_daily(data)
        log_scrape_run("youtube_daily", "success", rows)
        logger.info(f"YouTube Daily complete: {rows} rows saved")
    except Exception as exc:
        log_scrape_run("youtube_daily", "failed", error=str(exc))
        logger.error(f"YouTube Daily failed: {exc}")


def run_all():
    run_itunes()
    run_spotify()
    run_trending()
    run_artist_details()
    run_daily_charts()


def main():
    args = sys.argv[1:]

    if not args or args[0] == "help":
        print(__doc__)
        return

    if args[0] == "migrate":
        from src.database.migrate import run_migrations
        run_migrations()
        return

    if args[0] == "scrape":
        target = args[1] if len(args) > 1 else "all"

        if target in {"details", "artist_details"}:
            try:
                limit = int(args[2]) if len(args) > 2 else None
            except ValueError:
                logger.error("Artist detail limit must be an integer")
                sys.exit(1)
            run_artist_details(limit=limit)
            return

        dispatch = {
            "all": run_all,
            "itunes": run_itunes,
            "spotify": run_spotify,
            "trending": run_trending,
            "daily": run_daily_charts,
        }
        func = dispatch.get(target)
        if func is None:
            logger.error(f"Unknown scrape target: {target}")
            sys.exit(1)
        func()
        return

    if args[0] == "schedule":
        logger.info("Scheduling daily scrape at 10:55 UTC ...")
        sched.every().day.at("10:55").do(run_all)
        logger.info("Scheduler started. Press Ctrl+C to stop.")
        while True:
            sched.run_pending()
            time.sleep(60)
        
    logger.error(f"Unknown command: {args[0]}")
    print(__doc__)
    sys.exit(1)


if __name__ == "__main__":
    main()
