import unittest

from src.scrapers.itunes_scraper import build_profile_url
from src.scrapers.artist_details_scraper import (
    extract_item_name_from_summary,
    parse_artist_detail_page,
)


class ArtistDetailsParsingTests(unittest.TestCase):
    def test_build_profile_url_handles_relative_paths(self):
        self.assertEqual(
            build_profile_url("artist/bts.html"),
            "https://kworb.net/itunes/artist/bts.html",
        )

    def test_extract_item_name_from_summary_for_song_and_album(self):
        self.assertEqual(
            extract_item_name_from_summary("SWIM Spotify: #1 Argentina (=) #1 Peru (=)"),
            "SWIM",
        )
        self.assertEqual(
            extract_item_name_from_summary("Album: ARIRANG Spotify: #1 Argentina (=)"),
            "ARIRANG",
        )

    def test_parse_artist_detail_page_keeps_only_latin_american_countries(self):
        html = """
        <html>
          <head><title>Bad Bunny Chart Positions on Spotify, Apple Music and Other Streaming Services</title></head>
          <body>
            <div>2026-04-08 03:50 EDT</div>
            <table><tr><td>DtMF Spotify: #1 Argentina (=)</td></tr></table>
            <table><tr><td>NUEVAYoL Apple Music: #1 Mexico (=)</td></tr></table>
            <table><tr><td>Album: Debí Tirar Más Fotos Spotify: #1 Argentina (=)</td></tr></table>
            <table>
              <tr><td>Argentina iTunes : 1. DtMF</td></tr>
              <tr><td>Japan iTunes : 1. DtMF</td></tr>
              <tr><td>Mexico Spotify : 1. DtMF</td></tr>
            </table>
          </body>
        </html>
        """

        detail = parse_artist_detail_page(
            html=html,
            fallback_name="Bad Bunny",
            profile_url="https://kworb.net/itunes/artist/badbunny.html",
        )

        self.assertEqual(detail.countries_count, 2)
        self.assertEqual(detail.top_countries, "Argentina\nMexico")


if __name__ == "__main__":
    unittest.main()
