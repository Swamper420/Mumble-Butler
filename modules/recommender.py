"""History-aware, verification-scored music recommendation helper.

Kept backward compatible:
  MusicRecommender()._normalize_track / is_in_history /
  verify_track_on_itunes / get_recommendation / add_to_history
keep their original signatures. New QoL helpers are additive.
"""
import json
import os
import re
import threading
import time
import unicodedata

import requests

import config

SQUARE_BRACKETS_RE = re.compile(r'\[.*?\]')
NOISE_PARENS_RE = re.compile(
    r'\((?:[^\)]*(?:remaster|remastered|reissue|anniversary|live|deluxe|version|'
    r'edition|feat|ft|audio|video|edit|mix|official|lyric|visualiz|visualiser|'
    r'extended|radio|single|bonus|acoustic|instrumental|karaoke|cover|demo)[^\)]*)\)',
    re.IGNORECASE,
)
FEAT_CLAUSE_RE = re.compile(
    r'\b(?:feat(?:uring)?|ft)\.?\s+[^\-\(\[]+', re.IGNORECASE)
DASH_RE = re.compile(r'[–—−]')
NON_ALPHANUM_RE = re.compile(r'[^a-z0-9åäö\s]')
MULTI_SEP_RE = re.compile(r'\s*(?:\||//|›|»)\s*')

GENERIC_QUERIES = {
    "random music", "music", "musiikki", "musiikkia", "satunnainen musiikki",
    "random", "anything", "something", "good music", "hyvää musiikkia",
    "jotain", "jotain hyvää", "soita jotain", "laita jotain",
}

# Curated, known-good fallback catalog keyed by mood. Used when the LLM is
# offline or returns unusable candidates. All entries are real releases.
MOOD_CATALOG = {
    "chill": [
        "Tycho - A Walk",
        "Bonobo - Kerala",
        "The Midnight - Sunset",
        "Air - La Femme d'Argent",
        "Khruangbin - Maria También",
        "Sade - Smooth Operator",
    ],
    "focus": [
        "Miles Davis - So What",
        "John Coltrane - Naima",
        "Nils Frahm - Says",
        "Ólafur Arnalds - Near Light",
        "Daft Punk - Veridis Quo",
    ],
    "party": [
        "Daft Punk - One More Time",
        "ABBA - Dancing Queen",
        "Earth, Wind & Fire - September",
        "Jamiroquai - Cosmic Girl",
        "Mark Ronson - Uptown Funk",
    ],
    "rock": [
        "Queen - Bohemian Rhapsody",
        "Led Zeppelin - Stairway to Heaven",
        "The Rolling Stones - Gimme Shelter",
        "Foo Fighters - Everlong",
        "Arctic Monkeys - Do I Wanna Know?",
    ],
    "pop": [
        "Michael Jackson - Billie Jean",
        "Robyn - Dancing On My Own",
        "The Weeknd - Blinding Lights",
        "Dua Lipa - Don't Start Now",
        "Ariana Grande - Into You",
    ],
    "synthwave": [
        "Kavinsky - Nightcall",
        "The Midnight - Sunset",
        "College - A Real Hero",
        "Com Truise - Glawio",
        "Gunship - Tech Noir",
    ],
    "metal": [
        "Nightwish - Nemo",
        "Children of Bodom - Are You Dead Yet?",
        "Iron Maiden - Fear of the Dark",
        "Metallica - Master of Puppets",
        "Stam1na - Likainen parketti",
    ],
    "jazz": [
        "Miles Davis - So What",
        "John Coltrane - Giant Steps",
        "Dave Brubeck - Take Five",
        "Chet Baker - My Funny Valentine",
        "Ella Fitzgerald - Summertime",
    ],
    "finnish": [
        "Nightwish - Nemo",
        "Haloo Helsinki! - Maailma on tehty meitä varten",
        "JVG - Ikuinen vappu",
        "Pariisin Kevät - Kesäyö",
        "Vesala - Muitaki ihmisii",
        "Stam1na - Likainen parketti",
    ],
    "night": [
        "Kavinsky - Nightcall",
        "The Midnight - Sunset",
        "Massive Attack - Teardrop",
        "Portishead - Roads",
        "Burial - Archangel",
    ],
    "morning": [
        "Jack Johnson - Better Together",
        "Norah Jones - Don't Know Why",
        "Xavier Rudd - Follow the Sun",
        "Ben Howard - Only Love",
        "Vance Joy - Riptide",
    ],
}

FLAT_FALLBACK = [
    "Daft Punk - One More Time",
    "Queen - Bohemian Rhapsody",
    "The Midnight - Sunset",
    "Miles Davis - So What",
    "Kavinsky - Nightcall",
    "ABBA - Dancing Queen",
    "Bonobo - Kerala",
    "Nightwish - Nemo",
    "Tycho - A Walk",
    "Michael Jackson - Billie Jean",
    "Led Zeppelin - Stairway to Heaven",
    "Khruangbin - Maria También",
]

# vibe keyword -> catalog key
MOOD_KEYWORDS = {
    "chill": "chill", "chilli": "chill", "rauhall": "chill", "relax": "chill",
    "lofi": "chill", "ambient": "chill", "calm": "chill",
    "focus": "focus", "kood": "focus", "code": "focus", "study": "focus",
    "keskitty": "focus", "work": "focus", "työ": "focus",
    "party": "party", "bile": "party", "juhla": "party", "dance": "party",
    "tanssi": "party", "funk": "party", "disco": "party",
    "rock": "rock", "rockia": "rock", "kitara": "rock",
    "pop": "pop", "poppi": "pop",
    "synth": "synthwave", "syna": "synthwave", "wave": "synthwave",
    "retro": "synthwave", "80": "synthwave", "kasari": "synthwave",
    "metal": "metal", "hevi": "metal", "metalli": "metal",
    "jazz": "jazz", "blues": "jazz", "soul": "jazz",
    "suomi": "finnish", "finnish": "finnish", "kotim": "finnish",
    "iskelm": "finnish",
    "night": "night", "yö": "night", "ilta": "night", "evening": "night",
    "late": "night", "myöhä": "night",
    "morning": "morning", "aamu": "morning",
}


def _strip_accents(text):
    try:
        return ''.join(
            c for c in unicodedata.normalize('NFKD', text)
            if not unicodedata.combining(c)
        )
    except Exception:
        return text


class MusicRecommender:
    def __init__(self):
        self.history_file = config.MUSIC_HISTORY_FILE
        self.max_history = config.RECOMMENDER_MAX_HISTORY
        self.lock = threading.Lock()
        self.history = self._load_history()
        self.session = requests.Session()
        self._verify_cache = {}  # norm query -> (timestamp, result or None)

    # -- history ------------------------------------------------------
    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                return self._migrate_history(raw)
            except Exception as e:
                print(f"⚠️ Error loading music history: {e}")
        return []

    def _migrate_history(self, raw):
        """Accept legacy list[str] and new list[dict]; always return list[dict]."""
        if not isinstance(raw, list):
            return []
        migrated = []
        for entry in raw:
            if isinstance(entry, str):
                track = entry.strip()
                if not track:
                    continue
                artist, _ = self._split_artist_title(track)
                migrated.append({
                    "track": track,
                    "normalized": self._normalize_track(track),
                    "artist": self._normalize_artist(artist or ""),
                    "time": 0.0,
                    "vibe": "",
                })
            elif isinstance(entry, dict) and entry.get("track"):
                track = str(entry["track"]).strip()
                artist, _ = self._split_artist_title(track)
                migrated.append({
                    "track": track,
                    "normalized": entry.get("normalized") or self._normalize_track(track),
                    "artist": entry.get("artist") or self._normalize_artist(artist or ""),
                    "time": float(entry.get("time") or 0.0),
                    "vibe": str(entry.get("vibe") or ""),
                })
        # trim to max
        max_h = getattr(config, 'RECOMMENDER_MAX_HISTORY', 50) or 50
        return migrated[-max_h:]

    def _save_history(self):
        try:
            directory = os.path.dirname(self.history_file)
            if directory:
                os.makedirs(directory, exist_ok=True)
            tmp = self.history_file + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False)
            os.replace(tmp, self.history_file)
        except Exception as e:
            print(f"⚠️ Error saving music history: {e}")

    def _entry_track(self, e):
        if isinstance(e, dict):
            return e.get("track", "")
        return str(e) if isinstance(e, str) else ""

    def _entry_normalized(self, e):
        if isinstance(e, dict):
            return e.get("normalized") or self._normalize_track(e.get("track", ""))
        return self._normalize_track(e)

    def _entry_artist(self, e):
        if isinstance(e, dict):
            return e.get("artist", "")
        artist, _ = self._split_artist_title(e)
        return self._normalize_artist(artist or "")

    def _history_tracks(self):
        return [t for t in (self._entry_track(e) for e in self.history) if t]

    def add_to_history(self, track_name, vibe=""):
        if not track_name or not str(track_name).strip():
            return
        track = str(track_name).strip()
        artist, _ = self._split_artist_title(track)
        entry = {
            "track": track,
            "normalized": self._normalize_track(track),
            "artist": self._normalize_artist(artist or ""),
            "time": time.time(),
            "vibe": str(vibe or ""),
        }
        with self.lock:
            self.history = [e for e in self.history
                            if self._entry_normalized(e) != entry["normalized"]]
            self.history.append(entry)
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]
            snapshot = list(self.history)
        # save outside lock
        try:
            directory = os.path.dirname(self.history_file)
            if directory:
                os.makedirs(directory, exist_ok=True)
            tmp = self.history_file + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, ensure_ascii=False)
            os.replace(tmp, self.history_file)
        except Exception as e:
            print(f"⚠️ Error saving music history: {e}")

    def clear_history(self):
        with self.lock:
            self.history = []
        self._save_history()

    def remove_last(self):
        """Undo helper for '?dislike / ?undo song': drop most recent entry."""
        with self.lock:
            if not self.history:
                return None
            removed = self.history.pop()
        self._save_history()
        return self._entry_track(removed)

    def last_played(self):
        if not self.history:
            return None
        return self._entry_track(self.history[-1]) or None

    def history_summary(self, n=5):
        return [t for t in (self._entry_track(e) for e in self.history[-n:]) if t]

    # -- normalization -------------------------------------------------
    def _normalize_track(self, track_name):
        if not track_name:
            return ""
        normalized = str(track_name).strip().lower()
        normalized = DASH_RE.sub('-', normalized)
        normalized = MULTI_SEP_RE.sub(' - ', normalized)
        normalized = SQUARE_BRACKETS_RE.sub(' ', normalized)
        normalized = NOISE_PARENS_RE.sub(' ', normalized)
        normalized = FEAT_CLAUSE_RE.sub(' ', normalized)
        normalized = _strip_accents(normalized)
        normalized = NON_ALPHANUM_RE.sub(' ', normalized)
        return ' '.join(normalized.split())

    def _normalize_artist(self, artist):
        if not artist:
            return ""
        a = str(artist).strip().lower()
        a = SQUARE_BRACKETS_RE.sub(' ', a)
        a = FEAT_CLAUSE_RE.sub(' ', a)
        a = _strip_accents(a)
        a = NON_ALPHANUM_RE.sub(' ', a)
        # "The Beatles" == "Beatles" for cooldown purposes
        a = re.sub(r'^the\s+', '', ' '.join(a.split()))
        return a

    def _split_artist_title(self, track_str):
        """Split 'Artist - Title' on the most likely separator."""
        if not track_str:
            return (None, "")
        s = DASH_RE.sub('-', str(track_str).strip())
        # strip list numbering / bullets / quotes first
        s = re.sub(r'^[\d]+[\.\)\:\-\s]+', '', s).strip()
        s = re.sub(r'^[\-\*•\s]+', '', s).strip()
        s = s.strip(' "\'“”‘’')
        for sep in (" - ", " – ", " — ", " | ", " // "):
            if sep.strip() == "|":
                pass
            if sep in s:
                left, right = s.split(sep, 1)
                left, right = left.strip(' "\''), right.strip(' "\'')
                if left and right:
                    # guard against "Title - 2024 remaster" style tails
                    return (left, right)
        m = re.match(r'^(?P<artist>.+?)\s+by\s+(?P<title>.+)$', s, re.IGNORECASE)
        if m:
            return (m.group('title').strip(), m.group('artist').strip())
        if ":" in s and " - " not in s:
            left, right = s.split(":", 1)
            if left.strip() and right.strip():
                return (left.strip(), right.strip())
        return (None, s)

    def is_in_history(self, track_name, window=None):
        norm_track = self._normalize_track(track_name)
        if not norm_track:
            return False
        entries = self.history[-window:] if window else self.history
        for h in entries:
            if isinstance(h, dict):
                if h.get("normalized") == norm_track:
                    return True
            elif self._normalize_track(h) == norm_track:
                return True
        return False

    def is_artist_recent(self, track_name, window=None):
        """Cooldown: same artist played within last N tracks?"""
        if window is None:
            window = getattr(config, 'RECOMMENDER_ARTIST_COOLDOWN', 8)
        artist, _ = self._split_artist_title(track_name or "")
        key = self._normalize_artist(artist or "")
        if not key:
            return False
        recent = self.history[-window:] if window else self.history
        return any(self._entry_artist(e) == key for e in recent)

    def get_recent_artists(self, n=None):
        if n is None:
            n = getattr(config, 'RECOMMENDER_ARTIST_COOLDOWN', 8)
        return [a for a in (self._entry_artist(e) for e in self.history[-n:]) if a]

    # -- iTunes verification -------------------------------------------
    def _cache_get(self, key):
        ttl = getattr(config, 'RECOMMENDER_CACHE_TTL', 86400)
        hit = self._verify_cache.get(key)
        if not hit:
            return None, False
        ts, val = hit
        if ttl and (time.time() - ts) > ttl:
            self._verify_cache.pop(key, None)
            return None, False
        return val, True

    def _score_itunes_match(self, query_artist, query_title, result):
        """0..1 relevance of an iTunes result vs the query. Higher is better."""
        try:
            r_artist = str(result.get('artistName', '') or '')
            r_track = str(result.get('trackName', '') or '')
        except Exception:
            return 0.0
        rq = self._normalize_track(f"{query_artist} {query_title}" if query_artist else query_title)
        rr = self._normalize_track(f"{r_artist} {r_track}")
        if not rq or not rr:
            return 0.0
        q_tokens = set(rq.split())
        r_tokens = set(rr.split())
        if not q_tokens:
            return 0.0
        overlap = len(q_tokens & r_tokens) / max(1, len(q_tokens))
        score = overlap

        if query_artist:
            qa = self._normalize_artist(query_artist)
            ra = self._normalize_artist(r_artist)
            if qa and ra:
                if qa == ra:
                    score += 0.35
                elif qa in ra or ra in qa:
                    score += 0.2
                else:
                    # artist explicitly requested but completely different -> penalize
                    score -= 0.25
        if query_title:
            qt = self._normalize_track(query_title)
            rt = self._normalize_track(r_track)
            if qt and rt:
                if qt == rt or qt in rt or rt in qt:
                    score += 0.25
        # bonus for wrapperType track / kind song
        if str(result.get('kind', '')).lower() == 'song':
            score += 0.05
        # explicit penalty is mild; don't exclude outright
        if str(result.get('trackExplicitness', '')).lower() == 'explicit':
            score -= 0.03
        return max(0.0, min(1.0, score))

    def verify_track_on_itunes(self, track_str, return_meta=False):
        """
        Queries iTunes and returns canonical 'Artist - Title' for the best
        scoring result above threshold, else None. With return_meta=True
        returns (canonical, metadata_dict) or (None, None).
        """
        empty = (None, None) if return_meta else None
        if not track_str or not str(track_str).strip():
            return empty
        if str(track_str).strip().lower() in GENERIC_QUERIES:
            return empty

        query = str(track_str).strip()
        cache_key = self._normalize_track(query)
        cached, found = self._cache_get(cache_key)
        if found:
            if return_meta:
                if cached is None:
                    return (None, None)
                return (cached[0], cached[1])
            return cached

        artist, title = self._split_artist_title(query)
        threshold = float(getattr(config, 'RECOMMENDER_SCORE_THRESHOLD', 0.35))
        try:
            url = "https://itunes.apple.com/search"
            limit = int(getattr(config, 'RECOMMENDER_ITUNES_LIMIT', 10) or 10)
            limit = max(5, min(25, limit))
            timeout = getattr(config, 'RECOMMENDER_ITUNES_TIMEOUT', 5)
            params = {"term": query, "limit": limit, "entity": "song", "media": "music"}
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"⚠️ iTunes verification error for '{track_str}': {e}")
            # cache negative briefly? No — transient, don't poison cache.
            return empty

        try:
            results = data.get('results', []) or []
        except Exception:
            results = []

        best, best_score = None, 0.0
        for r in results:
            try:
                s = self._score_itunes_match(artist or "", title or query, r)
            except Exception:
                continue
            if s > best_score:
                best_score = s
                best = r

        if best is None or best_score < threshold:
            self._verify_cache[cache_key] = (time.time(), None)
            return empty

        canonical = f"{best.get('artistName')} - {best.get('trackName')}".strip(' -')
        meta = {
            "artist": best.get('artistName', ''),
            "title": best.get('trackName', ''),
            "genre": best.get('primaryGenreName', ''),
            "artwork": best.get('artworkUrl100', ''),
            "duration_ms": best.get('trackTimeMillis'),
            "score": round(best_score, 3),
        }
        self._verify_cache[cache_key] = (time.time(), (canonical, meta))
        if return_meta:
            return (canonical, meta)
        return canonical

    # -- selection ------------------------------------------------------
    def _clean_candidate(self, track):
        if not track or not isinstance(track, str):
            return None
        t = DASH_RE.sub('-', track.strip())
        t = re.sub(r'^[\d]+[\.\)\:\-\s]+', '', t).strip()
        t = re.sub(r'^[\-\*•\s]+', '', t).strip()
        t = t.strip(' "\'“”‘’').strip()
        # drop duration tails like "(3:45)" / "- 4:12"
        t = re.sub(r'\s*[\(\[]?\d{1,2}:\d{2}[\)\]]?\s*$', '', t).strip()
        if not t or len(t) < 3:
            return None
        if t.lower() in GENERIC_QUERIES:
            return None
        # require something resembling Artist - Title; single words are moods, not tracks
        if " - " not in t and "|" not in t and ":" not in t and " by " not in t.lower():
            # allow "Artist: Title" already handled; otherwise reject lone words
            if len(t.split()) < 2:
                return None
        return t

    def pick_fallback(self, vibe="", exclude_history=True):
        """Mood-mapped known-good track, history-filtered. Never returns None
        unless the catalog itself is empty."""
        key = self._match_mood(str(vibe or ""))
        pool = list(MOOD_CATALOG.get(key, [])) if key else []
        pool += [t for t in FLAT_FALLBACK if t not in pool]
        if exclude_history:
            fresh = [t for t in pool if not self.is_in_history(t)
                     and not self.is_artist_recent(t)]
            if fresh:
                return fresh[0]
            fresh_exact = [t for t in pool if not self.is_in_history(t)]
            if fresh_exact:
                return fresh_exact[0]
        return pool[0] if pool else None

    def _match_mood(self, vibe):
        v = _strip_accents(str(vibe or "").lower())
        for keyword, key in MOOD_KEYWORDS.items():
            if keyword in v:
                return key
        return ""

    def get_recommendations(self, candidates, count=3, allow_history_override=False, vibe=""):
        """Return up to `count` ranked, history-filtered track strings."""
        if not candidates:
            return []
        verify_enabled = getattr(config, 'RECOMMENDER_VERIFY', True)
        max_verify = int(getattr(config, 'RECOMMENDER_MAX_CANDIDATES_VERIFY', 8) or 8)

        # clean + dedupe preserving LLM order
        cleaned = []
        seen = set()
        for c in candidates:
            t = self._clean_candidate(c)
            if not t:
                continue
            norm = self._normalize_track(t)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            cleaned.append(t)
        if not cleaned:
            return []

        # verify top-N (LLM order) with scoring
        scored = []  # (canonical_or_orig, verified, score, idx)
        for idx, track in enumerate(cleaned[:max_verify] + cleaned[max_verify:]):
            if idx < max_verify and verify_enabled:
                canonical, meta = self.verify_track_on_itunes(track, return_meta=True)
                if canonical:
                    scored.append((canonical, True, (meta or {}).get("score", 0.6), idx))
                else:
                    scored.append((track, False, 0.0, idx))
            else:
                scored.append((track, False, 0.0, idx))

        # partition: fresh-verified > fresh-unverified > seen (oldest first)
        def history_age(canonical):
            norm = self._normalize_track(canonical)
            for i, e in enumerate(self.history):
                if self._entry_normalized(e) == norm:
                    return i  # lower = older
            return None

        fresh, seen_tracks = [], []
        for canonical, verified, score, idx in scored:
            age = history_age(canonical)
            artist_recent = self.is_artist_recent(canonical)
            if age is None and not (artist_recent and not allow_history_override):
                fresh.append((canonical, verified, score, idx))
            elif age is None and artist_recent:
                # artist cooldown hit: same artist but new song — prefer over
                # exact repeats (is_repeat=False sorts first).
                seen_tracks.append((canonical, verified, score, idx, False, 0))
            else:
                seen_tracks.append(
                    (canonical, verified, score, idx, True,
                     age if age is not None else 10 ** 9))

        fresh.sort(key=lambda x: (not x[1], -x[2], x[3]))  # verified, score, LLM order
        # same-artist-fresh before exact repeats; repeats oldest-first
        seen_tracks.sort(key=lambda x: (x[4], x[5], not x[1], -x[2], x[3]))

        ranked = ([c for c, _, _, _ in fresh]
                  + [c for c, _, _, _, _, _ in seen_tracks])
        if allow_history_override:
            # SPECIFIC request: trust LLM order, verified first
            ordered = sorted(scored, key=lambda x: (not x[1], -x[2], x[3]))
            ranked = [c for c, _, _, _ in ordered]

        # final: unique by normalized
        out, seen_norm = [], set()
        for t in ranked:
            n = self._normalize_track(t)
            if n in seen_norm:
                continue
            seen_norm.add(n)
            out.append(t)
            if len(out) >= count:
                break
        return out

    def get_recommendation(self, candidates, allow_history_override=False, vibe=""):
        """
        Takes a list of recommended track strings (e.g. ['Artist - Title', ...]) or fallback seeds,
        filters against history, optionally verifies on iTunes, and returns a selected track string.
        """
        if not candidates:
            # QoL: never return None when we have a catalog — fall back by vibe
            fallback = self.pick_fallback(vibe or "")
            if fallback:
                self.add_to_history(fallback, vibe=vibe or "")
                return fallback
            return None

        ranked = self.get_recommendations(
            candidates, count=1,
            allow_history_override=allow_history_override, vibe=vibe,
        )
        if ranked:
            self.add_to_history(ranked[0], vibe=vibe or "")
            return ranked[0]

        # Ultimate fallback: mood catalog (history-filtered) instead of None
        fallback = self.pick_fallback(vibe or "")
        if fallback:
            self.add_to_history(fallback, vibe=vibe or "")
            return fallback
        return None
