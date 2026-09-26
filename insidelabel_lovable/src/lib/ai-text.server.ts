/** Streams a text-only Responses call through the Lovable AI Gateway and returns the full text. */
export async function streamAiText(prompt: string): Promise<string> {
  const apiKey = process.env["LOVABLE_API_KEY"];
  if (!apiKey) throw new Error("AI is not configured on this server.");
  const response = await fetch("https://ai.gateway.lovable.dev/v1/responses", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
      "X-Lovable-AIG-SDK": "fetch",
    },
    body: JSON.stringify({
      model: "openai/gpt-6-astra",
      stream: true,
      store: false,
      reasoning: { effort: "low" },
      input: [{ role: "user", content: [{ type: "input_text", text: prompt }] }],
    }),
  });
  if (!response.ok) {
    const body = await response.text();
    console.error(`AI gateway failed [${response.status}]: ${body}`);
    if (response.status === 402) throw new Error("AI credits are used up. Add credits and try again.");
    if (response.status === 429) throw new Error("AI is busy right now. Wait a minute and try again.");
    throw new Error(`AI drafting is unavailable (${response.status}).`);
  }
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let text = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (!payload || payload === "[DONE]") continue;
        try {
          const evt = JSON.parse(payload);
          if (evt.type === "response.output_text.delta" && typeof evt.delta === "string") text += evt.delta;
        } catch {
          // partial frame
        }
      }
    }
  }
  return text;
}
