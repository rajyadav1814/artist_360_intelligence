"""
Shared country-scope definitions for Movement & Acquisition dashboards.

Maps human-readable country names to (spotify_country, itunes_country)
tuples used for querying the `spotify_daily`, `itunes_daily`, and
`itunes_artist_album` tables.
"""

# ── Latin American country scopes ────────────────────────────────
# ISO 3166-1 alpha-2 codes used by both kworb.net Spotify & iTunes charts
LATAM_COUNTRIES: dict[str, tuple[str, str]] = {
    "Argentina": ("ar", "ar"),
    "Bolivia": ("bo", "bo"),
    "Brazil": ("br", "br"),
    "Chile": ("cl", "cl"),
    "Colombia": ("co", "co"),
    "Costa Rica": ("cr", "cr"),
    "Cuba": ("cu", "cu"),
    "Dominican Republic": ("do", "do"),
    "Ecuador": ("ec", "ec"),
    "El Salvador": ("sv", "sv"),
    "Guatemala": ("gt", "gt"),
    "Honduras": ("hn", "hn"),
    "Mexico": ("mx", "mx"),
    "Nicaragua": ("ni", "ni"),
    "Panama": ("pa", "pa"),
    "Paraguay": ("py", "py"),
    "Peru": ("pe", "pe"),
    "Puerto Rico": ("pr", "pr"),
    "Uruguay": ("uy", "uy"),
    "Venezuela": ("ve", "ve"),
}

# ── Pre-built scope options for select boxes ─────────────────────
# Top-level / global scopes always listed first
GLOBAL_SCOPES: dict[str, tuple[str, str]] = {
    "Global / WW": ("global", "ww"),
    "United States": ("us", "us"),
}

# Combined scopes for dashboards that handle both Spotify & iTunes
COMBINED_SCOPES: dict[str, tuple[str, str]] = {
    **GLOBAL_SCOPES,
    **LATAM_COUNTRIES,
}

# iTunes-only scopes (album dashboards use itunes_artist_album only)
ITUNES_GLOBAL_SCOPES: dict[str, tuple[str, str]] = {
    "Global / WW": ("global", "ww"),
    "United States": ("us", "us"),
}

ITUNES_COMBINED_SCOPES: dict[str, tuple[str, str]] = {
    **ITUNES_GLOBAL_SCOPES,
    **LATAM_COUNTRIES,
}