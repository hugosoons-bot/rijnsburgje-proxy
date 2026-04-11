"""
Restaurant 't Rijnsburgje — Recipe Proxy
Vercel Serverless Function (Python)
Haalt receptpagina's op + pakt og:image meta tag voor afbeelding.
Extraheert ook JSON-LD (schema.org/Recipe) als die aanwezig is.
"""

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser
import json


class RecipeExtractor(HTMLParser):
    """Haalt leesbare tekst + og:image + JSON-LD Recipe schema uit HTML."""

    SKIP_TAGS = {"style", "nav", "header", "footer",
                 "aside", "noscript", "iframe", "form", "button", "svg"}

    def __init__(self):
        super().__init__()
        self.result = []
        self.image = None
        self._skip_depth = 0
        # JSON-LD tracking
        self._in_jsonld = False
        self._jsonld_buf = ""
        self.schema_recipe = None
        # Regular script tracking (skip content)
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == "meta" and not self.image:
            prop = attrs_dict.get("property", "") or attrs_dict.get("name", "")
            if prop in ("og:image", "twitter:image", "og:image:url"):
                self.image = attrs_dict.get("content") or None

        if tag == "script":
            stype = attrs_dict.get("type", "")
            if stype == "application/ld+json":
                self._in_jsonld = True
                self._jsonld_buf = ""
            else:
                self._in_script = True
            return

        if tag in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag == "script":
            if self._in_jsonld:
                self._parse_jsonld(self._jsonld_buf)
                self._in_jsonld = False
                self._jsonld_buf = ""
            self._in_script = False
            return

        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._in_jsonld:
            self._jsonld_buf += data
            return

        if self._in_script or self._skip_depth > 0:
            return

        text = data.strip()
        if len(text) > 1:
            self.result.append(text)

    def _parse_jsonld(self, raw):
        """Zoek naar schema.org/Recipe in een JSON-LD blok."""
        if self.schema_recipe:
            return  # Al gevonden
        try:
            data = json.loads(raw.strip())
        except Exception:
            return

        # Kan een enkel object of een @graph lijst zijn
        candidates = []
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            if "@graph" in data:
                candidates = data["@graph"]
            else:
                candidates = [data]

        for item in candidates:
            if not isinstance(item, dict):
                continue
            rtype = item.get("@type", "")
            if isinstance(rtype, list):
                rtype = " ".join(rtype)
            if "Recipe" in rtype:
                self.schema_recipe = item
                return

    def get_text(self):
        return "\n".join(self.result)


def extract_recipe_from_schema(schema: dict, url: str) -> dict:
    """Zet een schema.org/Recipe object om naar ons recept-formaat."""

    def txt(v):
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, dict):
            return v.get("text", v.get("name", "")).strip()
        if isinstance(v, list) and v:
            return txt(v[0])
        return ""

    def parse_ingredients(raw):
        items = []
        if not isinstance(raw, list):
            return items
        for ing in raw:
            s = txt(ing)
            if s:
                items.append({"naam": s, "hoeveelheid": 1, "eenheid": "x"})
        return items

    def parse_steps(raw):
        steps = []
        if not isinstance(raw, list):
            return steps
        for step in raw:
            if isinstance(step, str):
                steps.append(step.strip())
            elif isinstance(step, dict):
                # HowToStep or HowToSection
                stype = step.get("@type", "")
                if "Section" in stype:
                    # Section bevat itemListElement
                    for sub in step.get("itemListElement", []):
                        t = txt(sub)
                        if t:
                            steps.append(t)
                else:
                    t = txt(step)
                    if t:
                        steps.append(t)
        return steps

    def parse_yield(raw):
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str):
            digits = "".join(c for c in raw if c.isdigit())
            return int(digits) if digits else 4
        if isinstance(raw, list) and raw:
            return parse_yield(raw[0])
        return 4

    def parse_image(raw):
        if isinstance(raw, str):
            return raw
        if isinstance(raw, dict):
            return raw.get("url", "")
        if isinstance(raw, list) and raw:
            return parse_image(raw[0])
        return ""

    titel = txt(schema.get("name", ""))
    omschrijving = txt(schema.get("description", ""))
    ingredienten = parse_ingredients(schema.get("recipeIngredient", []))
    stappen = parse_steps(schema.get("recipeInstructions", []))
    personen = parse_yield(schema.get("recipeYield", 4))
    afbeelding = parse_image(schema.get("image", ""))
    keuken_raw = schema.get("recipeCuisine", "")
    keuken = txt(keuken_raw) if keuken_raw else ""

    return {
        "schema_recept": {
            "titel": titel,
            "omschrijving": omschrijving,
            "personen": personen,
            "ingredienten": ingredienten,
            "stappen": stappen,
            "keuken": keuken,
            "afbeelding": afbeelding,
            "bron": url,
        }
    }


class LinkExtractor(HTMLParser):
    """Haalt alle <a href> links met tekst uit een HTML-pagina."""

    SKIP_TAGS = {"script", "style", "nav", "footer", "aside", "noscript"}

    def __init__(self, base_url: str):
        super().__init__()
        parsed = urlparse(base_url)
        self.base = f"{parsed.scheme}://{parsed.netloc}"
        self.links = []
        self._skip_depth = 0
        self._cur_href = None
        self._cur_text = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "a" and self._skip_depth == 0:
            href = dict(attrs).get("href", "") or ""
            if href and not href.startswith(("javascript", "#", "mailto")):
                if href.startswith("http"):
                    self._cur_href = href
                elif href.startswith("/"):
                    self._cur_href = self.base + href
                else:
                    self._cur_href = None
            self._cur_text = []

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag == "a" and self._cur_href:
            text = " ".join(self._cur_text).strip()
            if text and len(text) > 3:
                self.links.append({"url": self._cur_href, "titel": text})
            self._cur_href = None
            self._cur_text = []

    def handle_data(self, data):
        if self._cur_href and self._skip_depth == 0:
            t = data.strip()
            if t:
                self._cur_text.append(t)


def fetch_links(url: str) -> dict:
    """Haal alle links op van een zoekresultatenpagina."""
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
            if "html" not in resp.headers.get("Content-Type", ""):
                return {"error": "Geen HTML pagina"}
            html = resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        return {"error": f"HTTP {e.code}"}
    except Exception as e:
        return {"error": str(e)}

    extractor = LinkExtractor(url)
    extractor.feed(html)

    parsed_base = urlparse(url)
    domain = parsed_base.netloc

    # Domein-matching: negeer www. prefix bij vergelijking
    def same_domain(href_netloc, base_netloc):
        return href_netloc.lstrip("www.") == base_netloc.lstrip("www.")

    # Paden die duidelijk geen recept zijn (navigatie, accounts, acties, etc.)
    NAV_PATRONEN = (
        "/tag/", "/tags/", "/category/", "/categorie/", "/author/", "/auteur/",
        "/page/", "/pagina/", "/?page", "/account", "/login", "/register",
        "/contact", "/about", "/zoeken", "/search", "/shop", "/winkel",
        "/cart", "/checkout", "/sitemap", "/feed", "/wp-",
        "/actie", "/acties", "/aanbieding", "/aanbiedingen",
        "/winactie", "/winacties", "/spaaractie", "/spaarprogramma",
        "/bonus", "/korting", "/folder", "/newsletter", "/nieuwsbrief",
        "/privacy", "/cookie", "/terms", "/voorwaarden",
        ".xml", ".json", "#", "?s=", "?q=", "?query=",
    )
    # Titels die wijzen op promotie/navigatie (hoofdletterongevoelig)
    NAV_TITELS = (
        "win ", "actie", "aanbieding", "spaar", "korting", "bonus",
        "nieuwsbrief", "abonneer", "inloggen", "registreer",
        "meer lezen", "lees meer", "read more", "bekijk alle",
        "terug naar", "home", "vorige", "volgende",
    )

    # Woorden die sterk wijzen op een receptpagina (in pad of titel)
    RECEPT_WOORDEN_PAD = ("recept", "recipe", "gerecht", "dish", "cook")

    seen = set()
    results = []
    for link in extractor.links:
        href = link["url"]
        parsed_href = urlparse(href)
        if not same_domain(parsed_href.netloc, domain):
            continue
        path = parsed_href.path.lower()
        if any(p in path or p in href.lower() for p in NAV_PATRONEN):
            continue
        # Titel moet minstens 5 tekens zijn en geen promotie/navigatielabel zijn
        titel = link["titel"].strip()
        titel_lower = titel.lower()
        if len(titel) < 5 or any(w in titel_lower for w in NAV_TITELS):
            continue
        # Accepteer als het pad recept-achtig is OF de titel lang genoeg is (echte receptnamen)
        pad_ok = any(w in path for w in RECEPT_WOORDEN_PAD)
        titel_ok = len(titel) > 15  # Echte receptnamen zijn doorgaans lang
        if not pad_ok and not titel_ok:
            continue
        if href in seen:
            continue
        seen.add(href)
        results.append(link)
        if len(results) >= 15:
            break

    return {"links": results}


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
        "text": text[:6000],
        "length": len(text),
    }

    if extractor.image:
        result["image"] = extractor.image

    # JSON-LD gevonden? Zet om naar ons formaat en stuur mee
    if extractor.schema_recipe:
        structured = extract_recipe_from_schema(extractor.schema_recipe, url)
        result.update(structured)

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
        mode = params.get("mode", ["full"])[0]

        if not url_param:
            self.send_json(400, {"error": "Geen URL meegegeven"})
            return

        url = unquote(url_param)
        if not url.startswith("http"):
            self.send_json(400, {"error": "Ongeldige URL"})
            return

        if mode == "links":
            result = fetch_links(url)
        else:
            result = fetch_and_extract(url)
        self.send_json(502 if "error" in result else 200, result)
