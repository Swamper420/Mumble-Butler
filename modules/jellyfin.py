import requests
import config
import random

class JellyfinClient:
    def __init__(self):
        # Graceful fallback
        if not hasattr(config, 'JELLYFIN'):
            self.enabled = False
            return

        self.base_url = config.JELLYFIN['BASE_URL'].rstrip('/')
        self.username = config.JELLYFIN['USERNAME']
        self.password = config.JELLYFIN['PASSWORD']
        self.api_key = config.JELLYFIN.get('API_KEY')
        self.enabled = True

        if not self.api_key:
            self._login()

    def _login(self):
        try:
            auth_url = f"{self.base_url}/Users/AuthenticateByName"
            headers = {
                "X-Emby-Authorization": 'MediaBrowser Client="MumbleBot", Device="MumbleBot", DeviceId="mumble-bot", Version="1.0.0"'
            }
            payload = {"Username": self.username, "Pw": self.password}

            r = requests.post(auth_url, json=payload, headers=headers)
            r.raise_for_status()
            self.api_key = r.json()['AccessToken']
            print(f"✅ Jellyfin Connected: {self.username}")
        except Exception as e:
            print(f"⚠️ Jellyfin Login Failed: {e}")
            self.enabled = False

    def get_random_track_seed(self):
        """Returns a tuple: (Title, Artist)"""
        if not self.enabled or not self.api_key:
            return None, None

        params = {
            "Recursive": "true",
            "IncludeItemTypes": "Audio",
            "SortBy": "Random",
            "Limit": 1,
            "Fields": "Path",
            "ExcludeLocationTypes": "Virtual",
            "api_key": self.api_key
        }

        try:
            r = requests.get(f"{self.base_url}/Items", params=params)
            r.raise_for_status()
            data = r.json()

            if data['TotalRecordCount'] > 0:
                item = data['Items'][0]
                title = item.get('Name', 'Unknown')
                artist = item.get('AlbumArtist', 'Unknown')

                # Return raw data so handler can format it
                return title, artist

            return None, None
        except Exception as e:
            print(f"⚠️ Jellyfin Seed Error: {e}")
            return None, None
