import urllib.parse
import re
import requests
import config

CLEAN_USER_PREFIX = re.compile(r'^User\s+.*?\s+(says|asks):\s*', re.IGNORECASE)
CLEAN_WAKEWORD = re.compile(r'^(obama|opama|opal|opa)[,\s]+', re.IGNORECASE)
CLEAN_SEARCH_VERB = re.compile(r'^(search|google|look up|find info for|find info on)\s+', re.IGNORECASE)


class WebSearcher:
    def __init__(self):
        self.enabled = getattr(config, 'WEB_SEARCH_ENABLED', True)
        self.default_max_results = getattr(config, 'WEB_SEARCH_MAX_RESULTS', 3)
        self.session = requests.Session()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

    def should_search(self, prompt: str) -> bool:
        """Determine if a prompt likely requires or benefits from real-time web search."""
        if not self.enabled:
            return False

        prompt_lower = prompt.lower().strip()

        # Exclude trivial small talk / greetings / conversational queries / math
        small_talk = [
            "hi", "hello", "hey", "how are you", "who are you", "what is your name",
            "what's your name", "thank you", "thanks", "bye", "goodbye", "good morning",
            "good night", "ping", "shut up", "stop", "forget", "undo", "help",
            "what can you do", "tell me a joke", "tell a joke", "sing a song"
        ]
        if prompt_lower in small_talk or prompt_lower.rstrip("?!.") in small_talk:
            return False

        # Skip short greetings or simple arithmetic
        words = prompt_lower.split()
        if len(words) <= 2 and all(w in ["hi", "hello", "hey", "obama", "bot", "there", "yo"] for w in words):
            return False

        # Skip simple arithmetic expressions (e.g. "what is 2+2")
        if re.search(r'^\s*(what\s+is\s+)?\d+[\s\+\-\*\/\^]+\d+\s*\??$', prompt_lower):
            return False

        # Direct search & real-time factual keywords
        explicit_triggers = [
            "search", "google", "look up", "find info", "browse",
            "weather", "news", "score", "stock price", "who won", "latest", "today",
            "current", "release date", "capital of", "president of", "prime minister",
            "schedule", "match result", "patch notes"
        ]
        if any(trig in prompt_lower for trig in explicit_triggers):
            return True

        # Factual query triggers
        factual_questions = (
            "who is ", "where is ", "when is ", "what is the price", "what time is",
            "what happened to", "how much is", "how to "
        )
        if prompt_lower.startswith(factual_questions):
            return True

        # Topic indicators
        topic_keywords = [
            "weather", "news", "score", "stock", "crypto", "election",
            "patch", "specs", "location", "address", "release date"
        ]
        if any(kw in prompt_lower for kw in topic_keywords):
            return True

        return False

    def search(self, query: str, max_results=None) -> list:
        """Perform DuckDuckGo web search and return a list of result dicts."""
        if not self.enabled or not query:
            return []

        if max_results is None:
            max_results = self.default_max_results

        # Strip user prefixes like "User <name> says:", wake words, and explicit search verbs
        clean_query = CLEAN_USER_PREFIX.sub('', query).strip()
        clean_query = CLEAN_WAKEWORD.sub('', clean_query).strip()
        clean_query = CLEAN_SEARCH_VERB.sub('', clean_query).strip()

        if not clean_query:
            clean_query = query

        try:
            url = "https://html.duckduckgo.com/html/"
            data = {"q": clean_query}
            response = self.session.post(url, data=data, headers=self.headers, timeout=6)
            response.raise_for_status()

            return self._parse_html_results(response.text, max_results=max_results)
        except Exception as e:
            print(f"⚠️ Web search error for query '{clean_query}': {e}")
            return []

    def _parse_html_results(self, html: str, max_results=3) -> list:
        results = []
        link_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL
        )
        snippet_pattern = re.compile(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL
        )

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i in range(min(len(links), max_results)):
            raw_url, raw_title = links[i]
            raw_snippet = snippets[i] if i < len(snippets) else ""

            actual_url = raw_url
            if "uddg=" in raw_url:
                parsed_query = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query)
                if "uddg" in parsed_query:
                    actual_url = parsed_query["uddg"][0]

            title = re.sub(r'<[^>]+>', '', raw_title).strip()
            snippet = re.sub(r'<[^>]+>', '', raw_snippet).strip()
            title = urllib.parse.unquote(title)

            if title and snippet:
                results.append({
                    "title": title,
                    "snippet": snippet,
                    "url": actual_url
                })

        return results

    def format_search_context(self, query: str, results: list) -> str:
        """Format search results into a clean string for LLM prompt insertion."""
        if not results:
            return ""

        context_lines = [f"[Real-time Web Search Context for: '{query}']"]
        for idx, res in enumerate(results, 1):
            context_lines.append(f"{idx}. {res['title']}")
            context_lines.append(f"   Snippet: {res['snippet']}")
            context_lines.append(f"   Source: {res['url']}")
        context_lines.append(
            "CRITICAL INSTRUCTION: Base your response strictly on the above real-time search context. "
            "Do not guess or make up facts not supported by the search results."
        )

        return "\n".join(context_lines)
