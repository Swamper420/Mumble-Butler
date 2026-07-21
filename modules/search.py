import urllib.parse
import re
import requests
import config


class WebSearcher:
    def __init__(self):
        self.enabled = getattr(config, 'WEB_SEARCH_ENABLED', True)
        self.default_max_results = getattr(config, 'WEB_SEARCH_MAX_RESULTS', 3)
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

        # Exclude trivial small talk / greetings / short conversational phrases
        small_talk = [
            "hi", "hello", "hey", "how are you", "who are you", "what is your name",
            "what's your name", "thank you", "thanks", "bye", "goodbye", "good morning",
            "good night", "ping", "shut up", "stop", "forget", "undo", "help"
        ]
        if prompt_lower in small_talk or prompt_lower.rstrip("?!.") in small_talk:
            return False

        # If prompt is a 1-2 word greeting (e.g. "hey obama"), skip
        words = prompt_lower.split()
        if len(words) <= 2 and all(w in ["hi", "hello", "hey", "obama", "bot", "there", "yo"] for w in words):
            return False

        # Direct search & factual keywords
        explicit_triggers = [
            "search", "google", "look up", "find info", "browse",
            "weather", "news", "score", "price", "who is", "what is", "where is",
            "when is", "how to", "who won", "latest", "today", "current", "release date",
            "capital of", "president", "prime minister", "definition", "stats", "schedule"
        ]
        if any(trig in prompt_lower for trig in explicit_triggers):
            return True

        # Any question starters or questions containing '?'
        question_starters = (
            "who", "what", "where", "when", "why", "how", "which",
            "is ", "are ", "did ", "does ", "can ", "has ", "have ", "tell me"
        )
        if prompt_lower.startswith(question_starters) or "?" in prompt:
            return True

        # Topic indicators
        topic_keywords = [
            "weather", "news", "score", "match", "stock", "price", "crypto",
            "event", "election", "release", "movie", "game", "winner", "result",
            "population", "update", "patch", "version", "specs", "location", "address"
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

        clean_query = re.sub(r'^(search|google|look up|find info for|find info on)\s+', '', query, flags=re.I).strip()
        if not clean_query:
            clean_query = query

        try:
            url = "https://html.duckduckgo.com/html/"
            data = {"q": clean_query}
            response = requests.post(url, data=data, headers=self.headers, timeout=6)
            response.raise_for_status()

            return self._parse_html_results(response.text, max_results=max_results)
        except Exception as e:
            print(f"⚠️ Web search error for query '{query}': {e}")
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
