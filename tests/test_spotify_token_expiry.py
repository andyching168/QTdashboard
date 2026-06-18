import json
import os
import tempfile
import unittest
from unittest.mock import patch

from spotipy.exceptions import SpotifyOauthError
from spotipy.oauth2 import SpotifyOAuth

from spotify.spotify_auth import (
    DashboardSpotifyOAuth,
    SpotifyAuthManager,
    SpotifyReauthorizationRequired,
    is_invalid_grant_error,
)


class SpotifyTokenExpiryTests(unittest.TestCase):
    def test_invalid_grant_detection(self):
        error = SpotifyOauthError("expired", error="invalid_grant")
        self.assertTrue(is_invalid_grant_error(error))
        self.assertFalse(is_invalid_grant_error(
            SpotifyOauthError("bad client", error="invalid_client")
        ))

    def test_oauth_converts_invalid_grant_to_reauthorization(self):
        notifications = []
        oauth = DashboardSpotifyOAuth(
            client_id="client",
            client_secret="secret",
            redirect_uri="http://127.0.0.1:8888/callback",
            invalid_grant_callback=notifications.append,
        )
        error = SpotifyOauthError("expired", error="invalid_grant")

        with patch.object(SpotifyOAuth, "refresh_access_token", side_effect=error):
            with self.assertRaises(SpotifyReauthorizationRequired):
                oauth.refresh_access_token("expired-refresh-token")

        self.assertEqual(notifications, [error])

    def test_manager_discards_cache_and_notifies_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "spotify_config.json")
            cache_path = os.path.join(temp_dir, ".spotify_cache")
            with open(config_path, "w", encoding="utf-8") as config_file:
                json.dump({
                    "client_id": "client",
                    "client_secret": "secret",
                    "redirect_uri": "http://127.0.0.1:8888/callback",
                }, config_file)
            with open(cache_path, "w", encoding="utf-8") as cache_file:
                cache_file.write("expired-token")

            notifications = []
            manager = SpotifyAuthManager(
                config_path=config_path,
                cache_path=cache_path,
                on_reauth_required=notifications.append,
            )
            error = SpotifyOauthError("expired", error="invalid_grant")

            manager._handle_invalid_grant(error)
            manager._handle_invalid_grant(error)

            self.assertFalse(os.path.exists(cache_path))
            self.assertTrue(manager.reauth_required)
            self.assertEqual(len(notifications), 1)


if __name__ == "__main__":
    unittest.main()
