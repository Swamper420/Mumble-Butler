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
        """Determine if a prompt likely requires real-time web search."""
        if not self.enabled:
            return False

        prompt_lower = prompt.lower().strip()

        # Direct explicit trigger keywords
        explicit_triggers = [
            "search", "google", "look up", "find info", "browse",
            "what is the weather", "weather in", "weather forecast",
            "latest news", "today's news", "who won", "live score",
            "current price", "stock price"
        ]
        if any(trig in prompt_lower for trig in explicit_triggers):
            return True

        # Temporal / real-time indicators
        temporal_keywords = [
            "today", "now", "yesterday", "this week", "latest", "recent", "current"
        ]
        topic_keywords = [
            "weather", "news", "score", "match", "stock", "price", "crypto",
            "event", "election", "release date", "movie", "movie schedule"
        ]

        has_temporal = any(kw in prompt_lower for kw in temporal_keywords)
        has_topic = any(kw in prompt_lower for kw in topic_keywords)

        return has_temporal and has_topic

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
        # Match result blocks in DuckDuckGo HTML
        # Links: <a class="result__a" href="...">title</a>
        # Snippets: <a class="result__snippet" ...>snippet</a>
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

            # Unquote DuckDuckGo redirect URL
            actual_url = raw_url
            if "uddg=" in raw_url:
                parsed_query = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query)
                if "uddg" in parsed_query:
                    actual_url = parsed_query["uddg"][0]

            # Strip HTML tags from title and snippet
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
        context_lines.append("Use the above real-time context to accurately answer the user's request.")

        return "\n".join(context_lines)
