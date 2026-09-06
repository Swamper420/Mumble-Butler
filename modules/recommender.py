"""History-aware music track resolution and recommendation.

Pipeline overview
-----------------
1. **Resolve** – turn a free-form query (``"bohemian rhapsody"``,
   ``"Queen - Bohemian Rhapsody"``, ``"Bohemian Rhapsody by Queen"``)
   into a canonical ``"Artist - Title"`` string via the iTunes Search API.
2. **Filter** – drop tracks already played recently (normalised comparison
   so ``"Queen - Bohemian Rhapsody [Official Video]"`` matches history).
3. **Pick** – choose with variety (shuffled by default) instead of always
   returning the first candidate, and fall back to a curated catalog when
   the network or the LLM is unavailable.

The public method names are kept backward compatible with the previous
version (``verify_track_on_itunes``, ``get_recommendation``,
``add_to_history``, ``is_in_history``) while new QoL helpers
(``resolve_track``, ``get_recommendations``, ``remove_from_history``,
``get_history`` …) are added on top.
"""

import json
import os
import random
import re
import threading
import time

import requests

import config


# --- Normalisation helpers -------------------------------------------------

SQUARE_BRACKETS_RE = re.compile(r'\[.*?\]')
NOISE_PARENS_RE = re.compile(
    r'\((?:[^\)]*(?:remaster|remix|live|deluxe|version|edition|feat|ft|audio|video|'
    r'edit|mix|official|lyric|visualizer|extended|radio|single|album|bonus|'
    r'explicit|acoustic|instrumental|karaoke)[^\)]*)\)',
    re.IGNORECASE,
)
FEAT_CLAUSE_RE = re.compile(
    r'\b(?:featuring|feat|ft)\.?\s+[^\s\-,;]+(?:\s+[^\s\-,;&]+){0,3}',
    re.IGNORECASE,
)
NON_ALPHANUM_RE = re.compile(r'[^a-z0-9\s]')
DASH_RE = re.compile(r'[–—−]')  # en/em dashes -> hyphen

#: Queries that carry no musical information on their own.
GENERIC_TERMS = frozenset({
    "random music", "music", "song", "songs", "tune", "tunes",
    "satunnainen musiikki", "musiikki", "musiikkia", "biisi", "kappale",
    "jotain", "jotain hyvää", "jotain hyvaa", "something", "anything",
    "whatever", "surprise me", "yllätä minut", "yllata minut", "yllätä", "yllata",
})

#: Curated fallback catalog used when the LLM and/or iTunes are unreachable.
#: Deliberately diverse across genres so repeated fallbacks still feel fresh.
CURATED_FALLBACKS = [
    "Daft Punk - One More Time",
    "Queen - Bohemian Rhapsody",
    "The Midnight - Sunset",
    "Miles Davis - So What",
    "Kavinsky - Nightcall",
    "ABBA - Dancing Queen",
    "Bonobo - Kerala",
    "Tycho - A Walk",
    "Daft Punk - Get Lucky",
    "Fleetwood Mac - Dreams",
    "Beastie Boys - Sabotage",
    "Nina Simone - Feeling Good",
    "Darude - Sandstorm",
    "Eagles - Hotel California",
    "Toto - Africa",
    "Portishead - Roads",
]

_GENERIC_NORMALIZED = None


def _generic_normalized():
    global _GENERIC_NORMALIZED
    if _GENERIC_NORMALIZED is None:
        _GENERIC_NORMALIZED = set()
        for term in GENERIC_TERMS:
            norm = NON_ALPHANUM_RE.sub(' ', term.lower()).strip()
            _GENERIC_NORMALIZED.add(' '.join(norm.split()))
    return _GENERIC_NORMALIZED


class MusicRecommender:
    def __init__(self, history_file=None, max_history=None):
        self.history_file = history_file or config.MUSIC_HISTORY_FILE
        self.max_history = max_history or config.RECOMMENDER_MAX_HISTORY
        self.lock = threading.RLock()
        self._history = []
        # O(1) dedup lookups; rebuilt whenever history changes.
        self._normalized_set = set()
        self.history = self._load_history()
        self.session = requests.Session()
        # term_norm -> (verified_string_or_None, timestamp)
        self._verify_cache = {}
        self._cache_order = []

    @property
    def history(self):
        return self._history

    @history.setter
    def history(self, value):
        # Setter keeps the normalized dedup index in sync even when callers
        # assign the list directly (e.g. tests, restores).
        self._history = list(value or [])
        self._normalized_set = {self._normalize_track(h) for h in self._history}

    # --- History persistence ------------------------------------------------

    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    tracks = []
                    for entry in data:
                        if isinstance(entry, dict):
                            t = entry.get("track")
                        else:
                            t = entry
                        if isinstance(t, str) and t.strip():
                            tracks.append(t.strip())
                    return tracks[-self.max_history:]
            except Exception as e:
                print(f"⚠️ Error loading music history: {e}")
        return []

    def _save_history(self):
        try:
            directory = os.path.dirname(self.history_file)
            if directory:
                os.makedirs(directory, exist_ok=True)
            tmp_path = self.history_file + ".tmp"
            with open(tmp_path, 'w') as f:
                json.dump(self.history, f)
            os.replace(tmp_path, self.history_file)
        except Exception as e:
            print(f"⚠️ Error saving music history: {e}")

    def _refresh_index(self):
        self._normalized_set = {self._normalize_track(h) for h in self.history}

    def add_to_history(self, track_name):
        """Append a track (MRU). Thread-safe, dedups case/noise-insensitively."""
        if not track_name or not track_name.strip():
            return
        track_name = track_name.strip()
        with self.lock:
            norm = self._normalize_track(track_name)
            self.history = [h for h in self.history
                            if self._normalize_track(h) != norm]
            self.history.append(track_name)
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]
            self._refresh_index()
            self._save_history()

    def remove_from_history(self, track_name):
        """QoL: never suggest this track again this session window ("dislike")."""
        if not track_name:
            return False
        with self.lock:
            norm = self._normalize_track(track_name)
            before = len(self.history)
            self.history = [h for h in self.history
                            if self._normalize_track(h) != norm]
            if len(self.history) != before:
                self._refresh_index()
                self._save_history()
                return True
            return False

    def clear_history(self):
        with self.lock:
            self.history = []
            self._normalized_set = set()
            self._save_history()

    def get_history(self, count=None):
        """Most recent tracks first (for ?history)."""
        with self.lock:
            hist = list(reversed(self.history))
        return hist[:count] if count else hist

    @property
    def last_played(self):
        with self.lock:
            return self.history[-1] if self.history else None

    # --- Normalisation ------------------------------------------------------

    def _normalize_track(self, track_name):
        if not track_name:
            return ""
        normalized = DASH_RE.sub('-', track_name).lower().strip()
        normalized = SQUARE_BRACKETS_RE.sub('', normalized)
        normalized = NOISE_PARENS_RE.sub('', normalized)
        normalized = FEAT_CLAUSE_RE.sub('', normalized)
        normalized = NON_ALPHANUM_RE.sub(' ', normalized)
        return ' '.join(normalized.split())

    def _split_artist_title(self, track_str):
        """Split 'Artist - Title' (any dash variant). Returns (artist, title)."""
        if not track_str:
            return "", ""
        cleaned = DASH_RE.sub('-', track_str).strip().strip('"\'“”‘’')
        if ' - ' in cleaned:
            artist, _, title = cleaned.partition(' - ')
            return artist.strip(), title.strip()
        # Fallback: 'Title by Artist' -> ('Artist', 'Title')
        m = re.match(r'^\s*(.+?)\s+by\s+(.+?)\s*$', cleaned, re.IGNORECASE)
        if m:
            return m.group(2).strip(), m.group(1).strip()
        return "", cleaned.strip()

    def is_generic_query(self, track_str):
        if not track_str:
            return True
        norm = self._normalize_track(track_str)
        return not norm or norm in _generic_normalized()

    def is_in_history(self, track_name):
        return self._normalize_track(track_name) in self._normalized_set

    # --- iTunes verification ------------------------------------------------

    def _cache_get(self, term_norm):
        entry = self._verify_cache.get(term_norm)
        if not entry:
            return None, False
        value, ts = entry
        ttl = getattr(config, 'RECOMMENDER_CACHE_TTL', 3600)
        if value is None and (time.time() - ts) > min(ttl, 600):
            # Negative entries expire quickly so transient misses can heal.
            self._verify_cache.pop(term_norm, None)
            return None, False
        if value is not None and (time.time() - ts) > ttl:
            self._verify_cache.pop(term_norm, None)
            return None, False
        return value, True

    def _cache_put(self, term_norm, value):
        max_size = getattr(config, 'RECOMMENDER_VERIFY_CACHE_SIZE', 200)
        if term_norm not in self._verify_cache:
            self._cache_order.append(term_norm)
            while len(self._cache_order) > max_size:
                oldest = self._cache_order.pop(0)
                self._verify_cache.pop(oldest, None)
        self._verify_cache[term_norm] = (value, time.time())

    def _score_result(self, term, artist, title):
        """Word-overlap score between the query and an iTunes candidate."""
        norm_term = set(self._normalize_track(term).split())
        if not norm_term:
            return 0.0
        norm_cand = set(self._normalize_track(f"{artist} - {title}").split())
        if not norm_cand:
            return 0.0
        overlap = len(norm_term & norm_cand) / len(norm_term)
        score = overlap
        # Bonus when the query names both artist and title words.
        term_artist, term_title = self._split_artist_title(term)
        artist_words = set(self._normalize_track(term_artist).split())
        title_words = set(self._normalize_track(term_title).split())
        cand_artist = set(self._normalize_track(artist).split())
        cand_title = set(self._normalize_track(title).split())
        if artist_words and artist_words & cand_artist:
            score += 0.25 * (len(artist_words & cand_artist) / len(artist_words))
        if title_words and title_words & cand_title:
            score += 0.25 * (len(title_words & cand_title) / len(title_words))
        if self._normalize_track(term) == self._normalize_track(f"{artist} - {title}"):
            score += 0.5
        return score

    def verify_track_on_itunes(self, track_str):
        """
        Resolve a track string to canonical 'Artist - Title' via iTunes.

        Picks the best-scoring result instead of blindly taking the first
        hit. Returns None for generic queries, empty results, or errors.
        Results are cached (positives long, negatives briefly).
        """
        if not track_str or self.is_generic_query(track_str):
            return None
        term = DASH_RE.sub('-', track_str).strip().strip('"\'“”‘’')
        if not term:
            return None
        term_norm = self._normalize_track(term)
        cached, hit = self._cache_get(term_norm)
        if hit:
            return cached

        try:
            url = "https://itunes.apple.com/search"
            limit = getattr(config, 'RECOMMENDER_ITUNES_LIMIT', 5)
            timeout = getattr(config, 'RECOMMENDER_ITUNES_TIMEOUT', 5)
            params = {
                "term": term,
                "limit": limit,
                "entity": "song",
                "media": "music",
            }
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            results = data.get('results', []) or []

            best, best_score = None, 0.0
            for track in results:
                artist = (track.get('artistName') or '').strip()
                title = (track.get('trackName') or '').strip()
                if not artist or not title:
                    continue
                score = self._score_result(term, artist, title)
                if score > best_score:
                    best, best_score = (artist, title), score

            verified = None
            if best and best_score >= 0.34:
                verified = f"{best[0]} - {best[1]}"
            self._cache_put(term_norm, verified)
            return verified
        except Exception as e:
            print(f"⚠️ iTunes verification error for '{track_str}': {e}")
            return None

    def resolve_track(self, query):
        """
        Canonicalize any user query to 'Artist - Title'.

        Returns the verified form when iTunes agrees, otherwise the cleaned
        original query (or None for generic/empty queries). Never raises.
        """
        if not query or self.is_generic_query(query):
            return None
        cleaned = DASH_RE.sub('-', query).strip().strip('"\'“”‘’')
        cleaned = re.sub(r'\s+', ' ', cleaned)
        if not cleaned:
            return None
        try:
            verified = self.verify_track_on_itunes(cleaned)
        except Exception:
            verified = None
        return verified or cleaned

    # --- Selection ----------------------------------------------------------

    def _verify_candidates(self, candidates):
        """Verify + dedupe candidates, preserving order. Never raises."""
        seen = set()
        verified_tracks = []
        for track in candidates or []:
            if not track or not track.strip():
                continue
            raw = track.strip()
            if self.is_generic_query(raw):
                continue
            try:
                verified = self.verify_track_on_itunes(raw)
            except Exception:
                verified = None
            final = verified or raw
            norm = self._normalize_track(final)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            verified_tracks.append(final)
        return verified_tracks

    def get_recommendations(self, candidates, count=1, allow_history_override=False):
        """
        Return up to *count* fresh tracks from *candidates*.

        Fresh (not recently played) tracks are preferred; when everything
        is stale the least-recent picks are recycled so something always
        plays. Returns [] only when no usable candidate exists at all.
        """
        count = max(1, int(count or 1))
        verified_tracks = self._verify_candidates(candidates)
        if not verified_tracks:
            return []

        if allow_history_override:
            pool = list(verified_tracks)
        else:
            pool = [t for t in verified_tracks if not self.is_in_history(t)]
            if not pool:
                pool = list(verified_tracks)

        shuffle = getattr(config, 'RECOMMENDER_SHUFFLE', True)
        if shuffle and len(pool) > 1:
            pool = random.sample(pool, len(pool))

        selected = pool[:count]
        for track in selected:
            self.add_to_history(track)
        return selected

    def get_recommendation(self, candidates, allow_history_override=False):
        """
        Return a single track string (backward-compatible wrapper).

        Falls back to a curated pick when *candidates* yield nothing.
        """
        selected = self.get_recommendations(
            candidates,
            count=1,
            allow_history_override=allow_history_override,
        )
        if selected:
            return selected[0]
        fallback = self.recommend_fallback()
        if fallback:
            return fallback
        # Absolute last resort: echo the first usable candidate.
        for track in candidates or []:
            if track and track.strip() and not self.is_generic_query(track):
                cleaned = track.strip()
                self.add_to_history(cleaned)
                return cleaned
        return None

    def recommend_fallback(self, exclude_history=True):
        """Pick a curated track, preferring ones not played recently."""
        fallbacks = list(getattr(config, 'RECOMMENDER_FALLBACK_TRACKS', None)
                         or CURATED_FALLBACKS)
        pool = ([t for t in fallbacks if not self.is_in_history(t)]
                if exclude_history else list(fallbacks))
        if not pool:
            pool = list(fallbacks)
        if not pool:
            return None
        selection = random.choice(pool)
        try:
            verified = self.verify_track_on_itunes(selection)
        except Exception:
            verified = None
        final = verified or selection
        self.add_to_history(final)
        return final
