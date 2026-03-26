"""
Restaurant 't Rijnsburgje — Recipe Proxy
Vercel Serverless Function (Python)
Haalt receptpagina's op + pakt og:image meta tag voor afbeelding
"""

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser
import json


class RecipeExtractor(HTMLParser):
    """Haalt leesbare tekst + og:image uit HTML."""

    SKIP_TAGS = {"script", "style", "nav", "header", "footer",
                 "aside", "noscript", "iframe", "form", "button", "svg"}

    def __init__(self):
        super().__init__()
        self.result = []
        self.image = None
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "meta" and not self.image:
            attrs_dict = dict(attrs)
            prop = attrs_dict.get("property", "") or attrs_dict.get("name", "")
            if prop in ("og:image", "twitter:image", "og:image:url"):
                self.image = attrs_dict.get("content") or None

        if tag in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if len(text) > 1:
                self.result.append(text)

    def get_text(self):
        return "\n".join(self.result)


def fetch_and_extract(url: str) -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }

    req = Request(url, headers=headers)

    try:
        with urlopen(req, timeout=12) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "html" not in content_type:
                return {"error": f"Geen HTML pagina ({content_type})"}
            html = resp.read().decode("utf-8", errors="replace")

    except HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except URLError as e:
        return {"error": f"Kon pagina niet bereiken: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}

    extractor = RecipeExtractor()
    extractor.feed(html)
    text = extractor.get_text()

    if len(text) < 100:
        return {"error": "Pagina te kort of leeg"}

    result = {
        "url": url,
        "text": text[:5000],
        "length": len(text),
    }

    if extractor.image:
        result["image"] = extractor.image

    return result


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
}


class handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path in ("/api/health", "/health"):
            self.send_json(200, {"status": "ok"})
            return

        params = parse_qs(parsed.query)
        url_param = params.get("url", [None])[0]

        if not url_param:
            self.send_json(400, {"error": "Geen URL meegegeven"})
            return

        url = unquote(url_param)
        if not url.startswith("http"):
            self.send_json(400, {"error": "Ongeldige URL"})
            return

        result = fetch_and_extract(url)
        self.send_json(502 if "error" in result else 200, result)
