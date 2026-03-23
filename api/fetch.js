export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  if (req.method === "OPTIONS") return res.status(200).end();

  const url = req.query.url;
  if (!url) return res.status(400).json({ error: "Geen URL meegegeven" });
  if (!url.startsWith("http")) return res.status(400).json({ error: "Ongeldige URL" });

  if (req.query.health || req.url.includes("health")) {
    return res.status(200).json({ status: "ok", service: "Rijnsburgje proxy" });
  }

  try {
    const response = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "nl-NL,nl;q=0.9",
        "Accept": "text/html,*/*;q=0.8",
      }
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const html = await response.text();

    // Verwijder scripts, styles en tags
    const clean = html
      .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "")
      .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 8000);

    if (clean.length < 100) throw new Error("Pagina te kort of leeg");

    return res.status(200).json({ url, text: clean, length: clean.length });
  } catch (err) {
    return res.status(502).json({ error: err.message });
  }
}
