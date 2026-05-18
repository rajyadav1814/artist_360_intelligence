from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional


@dataclass
class Artist:
    name: str
    profile_url: Optional[str] = None
    id: Optional[int] = None


@dataclass
class ItunesRanking:
    artist_name: str
    rank: int
    rank_change: Optional[str] = None
    total_points: Optional[int] = None
    itunes_points: Optional[int] = None
    spotify_points: Optional[int] = None
    apple_music_points: Optional[int] = None
    shazam_points: Optional[int] = None
    youtube_points: Optional[int] = None
    other_points: Optional[int] = None
    top_country: Optional[str] = None
    num_countries: Optional[int] = None
    profile_url: Optional[str] = None
    scrape_date: date = field(default_factory=date.today)


@dataclass
class SpotifyArtist:
    artist_name: str
    monthly_listeners: Optional[int] = None
    peak_listeners: Optional[int] = None
    peak_date: Optional[date] = None
    scrape_date: date = field(default_factory=date.today)


@dataclass
class TrendingArtist:
    artist_name: str
    source: str
    rank: int
    rank_change: Optional[str] = None
    total_points: Optional[int] = None
    top_country: Optional[str] = None
    month: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m"))


@dataclass
class ArtistDetail:
    artist_name: str
    profile_url: str
    page_title: Optional[str] = None
    snapshot_text: Optional[str] = None
    songs_count: int = 0
    albums_count: int = 0
    countries_count: int = 0
    top_songs: Optional[str] = None
    top_albums: Optional[str] = None
    top_countries: Optional[str] = None
    scrape_date: date = field(default_factory=date.today)


@dataclass
class SpotifyDaily:
    date: date
    country: str
    rank: int
    artist_title: str
    days: Optional[int] = None
    peak: Optional[int] = None
    streams: Optional[int] = None
    streams_change: Optional[int] = None
    total_streams: Optional[int] = None
    label: Optional[str] = None


@dataclass
class ItunesDaily:
    date: date
    country: str
    rank: int
    artist_title: str
    days: Optional[int] = None
    peak: Optional[int] = None
    points: Optional[int] = None
    points_change: Optional[int] = None
    total_points: Optional[int] = None
    label: Optional[str] = None
    rank_change: Optional[str] = None


@dataclass
class ItunesArtistAlbum:
    date: date
    country: str
    rank: int
    artist_title: str
    days: Optional[int] = None
    peak: Optional[int] = None
    points: Optional[int] = None
    points_change: Optional[int] = None
    total_points: Optional[int] = None
    label: Optional[str] = None
    rank_change: Optional[str] = None





