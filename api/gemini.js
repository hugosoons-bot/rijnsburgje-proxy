export const config = { api: { bodyParser: { sizeLimit: '10mb' } } };

export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") return res.status(200).end();
  if (req.method !== "POST") return res.status(405).json({ error: "Alleen POST" });

  try {
    const body = typeof req.body === "string" ? JSON.parse(req.body) : req.body;
    const { system, messages, max_tokens } = body;

    // Convert Anthropic messages format → Gemini format
    const contents = messages.map(msg => {
      const parts = [];
      if (typeof msg.content === "string") {
        parts.push({ text: msg.content });
      } else if (Array.isArray(msg.content)) {
        for (const block of msg.content) {
          if (block.type === "text") {
            parts.push({ text: block.text });
          } else if (block.type === "image") {
            parts.push({ inline_data: { mime_type: block.source.media_type, data: block.source.data } });
          }
        }
      }
      return { role: msg.role === "assistant" ? "model" : "user", parts };
    });

    const geminiBody = {
      ...(system ? { system_instruction: { parts: [{ text: system }] } } : {}),
      contents,
      generationConfig: { maxOutputTokens: max_tokens || 1200 }
    };

    const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${process.env.GEMINI_API_KEY}`;
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(geminiBody)
    });

    const data = await response.json();

    if (!response.ok) {
      return res.status(response.status).json({ error: { message: data.error?.message || "Gemini API fout" } });
    }

    // Convert Gemini response → Anthropic-compatible format (frontend verwacht dit)
    const text = data.candidates?.[0]?.content?.parts?.map(p => p.text || "").join("") || "";
    return res.status(200).json({ content: [{ type: "text", text }] });

  } catch (err) {
    return res.status(500).json({ error: { message: err.message } });
  }
}
