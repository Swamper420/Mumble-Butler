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
        # Strip square brackets like [Official Video], [HD], etc.
        normalized = re.sub(r'\[.*?\]', '', normalized)
        # Strip parens containing common noise like (remaster...), (live...), (feat...)
        normalized = re.sub(r'\((?:[^\)]*(?:remaster|live|deluxe|version|edition|feat|ft|audio|video|edit|mix)[^\)]*)\)', '', normalized)
        # Strip standalone feat / ft clauses
        normalized = re.sub(r'\b(?:feat|ft)\.?\s+[^\s-]+', '', normalized)
        # Clean non-alphanumeric chars
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
        if not track_str or track_str.lower() in ("random music", "music"):
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

    def get_recommendation(self, candidates, allow_history_override=False):
        """
        Takes a list of recommended track strings (e.g. ['Artist - Title', ...]) or fallback seeds,
        filters against history, optionally verifies on iTunes, and returns a selected track string.
        """
        if not candidates:
            return None

        # Filter out history
        available_tracks = []
        for track in candidates:
            if not track or track.lower() in ("random music", "music"):
                continue
            
            # Standardize / verify on iTunes if possible
            verified = self.verify_track_on_itunes(track)
            final_track = verified if verified else track.strip()

            if allow_history_override or not self.is_in_history(final_track):
                available_tracks.append(final_track)

        if available_tracks:
            selection = available_tracks[0]
            self.add_to_history(selection)
            return selection

        # Fallback if all candidates were in history: pick first candidate
        fallback_track = candidates[0].strip()
        verified = self.verify_track_on_itunes(fallback_track)
        selection = verified if verified else fallback_track
        self.add_to_history(selection)
        return selection


