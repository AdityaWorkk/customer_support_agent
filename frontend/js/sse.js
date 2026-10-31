import { state } from "./store.js";
import { BASE, ApiError, refreshSession } from "./api.js";

/** POST + stream Server-Sent Events (EventSource can't POST or send auth headers). */
export async function streamPost(path, body, handlers = {}) {
  const go = () => fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${state.token}` },
    body: JSON.stringify(body),
  });
  let r;
  try { r = await go(); } catch { throw new ApiError("Can't reach the server. Try again in a few seconds.", 0, "network"); }
  if (r.status === 401 && await refreshSession()) r = await go();
  if (!r.ok) {
    let d = {}; try { d = await r.json(); } catch { /* ignore */ }
    throw new ApiError(d.message || "Message could not be sent.", r.status, d.error);
  }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, i); buf = buf.slice(i + 2);
      let ev = "message", data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) ev = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) { try { handlers[ev]?.(JSON.parse(data)); } catch { /* ignore malformed frame */ } }
    }
  }
}
