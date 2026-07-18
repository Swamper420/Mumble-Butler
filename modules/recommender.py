import requests
import random
import json
import os
import config

class MusicRecommender:
    def __init__(self):
        self.history_file = config.MUSIC_HISTORY_FILE
        self.max_history = config.RECOMMENDER_MAX_HISTORY
        self.history = self._load_history()

    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Error loading music history: {e}")
        return []

    def _save_history(self):
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f)
        except Exception as e:
            print(f"⚠️ Error saving music history: {e}")

    def add_to_history(self, track_name):
        if track_name in self.history:
            self.history.remove(track_name)
        self.history.append(track_name)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        self._save_history()

    def _normalize_track(self, track_name):
        if not track_name:
            return ""
        import re
        normalized = track_name.lower().strip()
        normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)
        return ' '.join(normalized.split())

    def is_in_history(self, track_name):
        norm_track = self._normalize_track(track_name)
        for h in self.history:
            if self._normalize_track(h) == norm_track:
                return True
        return False

    def verify_track_on_itunes(self, track_str):
        """
        Queries iTunes with a track string (e.g., 'Artist - Title') to see if it exists.
        Returns the formatted 'Artist - Title' from iTunes if found, or None otherwise.
        """
        if not track_str or track_str.lower() == "random music":
            return None
        try:
            url = "https://itunes.apple.com/search"
            params = {
                "term": track_str,
                "limit": 3,
                "entity": "song",
                "media": "music"
            }
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()

            results = data.get('results', [])
            if results:
                track = results[0]
                return f"{track.get('artistName')} - {track.get('trackName')}"
        except Exception as e:
            print(f"⚠️ iTunes verification error for '{track_str}': {e}")
        return None

    def get_recommendation(self, seeds):
        """
        Takes a list of seeds (artists, genres, or keywords) and returns a 'Artist - Title' string.
        Seeds should be provided in priority order.
        """
        if not seeds:
            return None

        # Keep track of first seed's results for fallback if everything is in history
        first_seed_all_tracks = []

        for idx, seed in enumerate(seeds):
            # Try iTunes Search API
            try:
                # Use 'music' entity to get songs
                url = "https://itunes.apple.com/search"
                params = {
                    "term": seed,
                    "limit": 20,
                    "entity": "song",
                    "media": "music"
                }
                response = requests.get(url, params=params, timeout=5)
                response.raise_for_status()
                data = response.json()

                results = data.get('results', [])
                if not results:
                    continue

                # Filter out history
                available_tracks = []
                for track in results:
                    track_str = f"{track.get('artistName')} - {track.get('trackName')}"
                    if idx == 0:
                        first_seed_all_tracks.append(track_str)
                    if not self.is_in_history(track_str):
                        available_tracks.append(track_str)

                if available_tracks:
                    # Pick a random one from the available tracks
                    selection = random.choice(available_tracks)
                    self.add_to_history(selection)
                    return selection

            except Exception as e:
                print(f"⚠️ Recommender API error for seed '{seed}': {e}")
                continue

        # Fallback if everything is in history, but we have first_seed results
        if first_seed_all_tracks:
            selection = random.choice(first_seed_all_tracks)
            self.add_to_history(selection)
            return selection

        return None

