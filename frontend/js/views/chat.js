import { api, fetchBlobUrl } from "../api.js";
import { streamPost } from "../sse.js";
// import { h, clear, renderText, toast, money, fmtDate, fill } from "../ui.js";
import { h, clear, renderText, toast, money, fmtDate, fill } from "../ui.js";
import { waybill } from "../components/waybill.js";
import { ticket, costLedger } from "../components/ticket.js";

const PROMPTS = ["Where is my latest order?", "I want to cancel an order", "My product arrived damaged", "Show the cost breakdown for my order"];

function card(ui) {
  if (ui.type === "waybill") return waybill(ui.order);
  if (ui.type === "ticket") return ticket(ui.complaint);
  if (ui.type === "cost") return costLedger(ui.breakdown);
  if (ui.type === "order_list") return h("ul", { class: "mini-list" }, ui.orders.map((o) => h("li", {},
    h("span", { class: "mono", text: o.id }), h("span", { text: o.items.join(", ") }), h("span", { class: "mono muted", text: `${o.status.replaceAll("_", " ")}` }))));
  if (ui.type === "attachment") { const img = h("img", { class: "attach-img", alt: "Your attached photo" }); loadImg(img, ui.url); return img; }
  return document.createDocumentFragment();
}
async function loadImg(img, url) {
  try { img.src = url.startsWith("/api") ? await fetchBlobUrl(url) : url; } catch { img.replaceWith(h("span", { class: "muted", text: "Photo unavailable" })); }
}

export function mount(root, { params, navigate }) {
  let sid = params[0] || null, lastId = null, busy = false, attachment = null, alive = true;
  const seen = new Set();

  const rail = h("aside", { class: "rail", "aria-label": "Chat history" });
  const inner = h("div", { class: "thread-inner" });
  const thread = h("div", { class: "thread", role: "log", "aria-live": "polite" }, inner);
  const input = h("textarea", { rows: 1, placeholder: "Ask about an order, a refund or a problem", "aria-label": "Your message", maxlength: 2000 });
  const sendBtn = h("button", { class: "btn primary", type: "button", text: "Send" });
  const file = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", hidden: true });
  const clip = h("button", { class: "btn", type: "button", "aria-label": "Attach a photo", title: "Attach a photo", text: "Photo" });
  const chipBox = h("div");
  const toggle = h("button", { class: "btn rail-toggle", type: "button", text: "History", onclick: () => rail.classList.toggle("open") });

  root.replaceChildren(h("div", { class: "chat" }, rail,
    h("div", { class: "thread-wrap" }, thread,
      h("div", { class: "composer" }, chipBox, h("div", { class: "composer-in" }, clip, input, sendBtn), file))));
  root.querySelector(".composer").prepend(h("div", { class: "rail-toggle-row" }, toggle));

  const scroll = () => { thread.scrollTop = thread.scrollHeight; };

  function bubble(role, text, cards = [], author = null) {
    if (role === "assistant" && author === "system") return inner.append(h("div", { class: "msg sys", text })), scroll();
    const m = h("div", { class: `msg ${role === "user" ? "user" : "bot"}` });
    if (author === "admin") m.append(h("div", { class: "who", text: "Support agent" }));
    const t = h("div", { class: "txt" }); renderText(t, text || ""); if (text) m.append(t);
    if (cards.length) m.append(h("div", { class: "cards" }, cards.map(card)));
    inner.append(m); scroll(); return m;
  }

  function empty() {
    clear(inner).append(h("div", { class: "empty" }, h("h2", { text: "How can we help?" }),
      h("p", { class: "muted", text: "Order tracking, cancellations, refunds, damaged items and complaints." }),
      h("div", { class: "prompts" }, PROMPTS.map((p) => h("button", { class: "btn", type: "button", text: p, onclick: () => send(p) })))));
  }

  // async function loadRail() {
  //   let list = []; try { list = await api("/chat/sessions"); } catch { /* keep empty */ }
  //   fill(rail, h("button", { class: "btn", type: "button", text: "New chat", onclick: () => { rail.classList.remove("open"); navigate("#/chat"); } }),
  //     list.length ? null : h("p", { class: "muted", text: "Your past chats will appear here." }),
  //     list.map((s) => h("button", { class: "rail-item", type: "button", "aria-current": s.id === sid, onclick: () => { rail.classList.remove("open"); navigate(`#/chat/${s.id}`); } },
  //       h("span", { class: "rail-title", text: s.title }), h("span", { class: "rail-date", text: fmtDate(s.updated_at, true) }))));
  // }
  async function loadRail() {
    let list = []; try { list = await api("/chat/sessions"); } catch { /* keep empty */ }
    fill(rail, h("button", { class: "btn", type: "button", text: "New chat", onclick: () => { rail.classList.remove("open"); navigate("#/chat"); } }),
      list.length ? null : h("p", { class: "muted", text: "Your past chats will appear here." }),
      list.map((s) => h("button", { class: "rail-item", type: "button", "aria-current": s.id === sid, onclick: () => { rail.classList.remove("open"); navigate(`#/chat/${s.id}`); } },
        h("span", { class: "rail-title", text: s.title }), h("span", { class: "rail-date", text: fmtDate(s.updated_at, true) }))));
  }

  function confirmCard(p) {
    const keep = h("button", { class: "btn", type: "button", text: "Keep order" });
    const go = h("button", { class: "btn primary", type: "button", text: "Confirm cancellation" });
    const box = h("div", { class: "confirm", role: "group", "aria-label": "Confirm cancellation" },
      h("h3", { text: `Cancel ${p.order_id}?` }),
      h("div", { class: "row" }, h("span", { text: "Order total" }), h("span", { class: "mono", text: money(p.total, p.currency) })),
      p.retained_delivery_fee ? h("div", { class: "row" }, h("span", { text: "Delivery charge kept" }), h("span", { class: "mono", text: `− ${money(p.retained_delivery_fee, p.currency)}` })) : null,
      h("div", { class: "row" }, h("strong", { text: "You get back" }), h("strong", { class: "mono", text: money(p.refund_amount, p.currency) })),
      h("div", { class: "actions" }, go, keep));
    const decide = async (approved) => {
      keep.disabled = go.disabled = true;
      box.replaceWith(h("div", { class: "msg user", text: approved ? "Yes, cancel it." : "Keep my order." }));
      await run(() => streamPost(`/chat/sessions/${sid}/confirm`, { approved }, handlers()));
    };
    go.onclick = () => decide(true); keep.onclick = () => decide(false);
    inner.append(box); scroll();
  }

  let cur = null, curText = "";
  function handlers() {
    cur = null; curText = "";
    const ensure = () => cur ??= bubble("assistant", "", [], "bot");
    return {
      token: ({ text }) => { const m = ensure(); curText += text; let t = m.querySelector(".txt"); if (!t) { t = h("div", { class: "txt caret" }); m.prepend(t); } t.classList.add("caret"); renderText(t, curText); t.classList.add("caret"); scroll(); },
      card: (ui) => { const m = ensure(); let c = m.querySelector(".cards"); if (!c) { c = h("div", { class: "cards" }); m.append(c); } c.append(card(ui)); scroll(); },
      confirm: (p) => confirmCard(p),
      handoff: ({ message }) => bubble("assistant", message, [], "system"),
      error: () => {},
      done: () => cur?.querySelector(".caret")?.classList.remove("caret"),
    };
  }

  async function run(fn) {
    busy = true; sendBtn.disabled = true;
    try { await fn(); } catch (x) { toast(x.message, true); }
    finally { cur?.querySelector(".caret")?.classList.remove("caret"); busy = false; sendBtn.disabled = false; await sync(); loadRail(); input.focus(); }
  }

  async function send(text) {
    text = (text ?? input.value).trim();
    if (!text || busy) return;
    if (!sid) {
      try { sid = (await api("/chat/sessions", { method: "POST" })).id; history.replaceState(null, "", `#/chat/${sid}`); }
      catch (x) { return toast(x.message, true); }
    }
    if (!inner.querySelector(".msg, .confirm")) clear(inner);
    const att = attachment; attachment = null; chipBox.replaceChildren();
    bubble("user", text, att ? [{ type: "attachment", url: att.url }] : []);
    input.value = ""; autosize();
    await run(() => streamPost(`/chat/sessions/${sid}/messages`, { content: text, attachment_id: att?.id ?? null }, handlers()));
  }

  /* Pull in messages we didn't render ourselves: admin replies, review decisions, errors. */
  async function sync() {
    if (!sid || !alive) return;
    try {
      const d = await api(`/chat/sessions/${sid}/messages${lastId ? `?after=${lastId}` : ""}`);
      for (const m of d.messages) {
        lastId = m.id;
        if (seen.has(m.id)) continue; seen.add(m.id);
        if (m.author === "admin" || m.author === "system") bubble("assistant", m.content, m.cards, m.author);
      }
    } catch { /* transient */ }
  }

  function autosize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 144) + "px"; }
  input.addEventListener("input", autosize);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
  sendBtn.onclick = () => send();
  clip.onclick = () => file.click();
  file.onchange = async () => {
    const f = file.files[0]; file.value = ""; if (!f) return;
    const fd = new FormData(); fd.append("file", f);
    try {
      const a = await api("/complaints/attachments", { method: "POST", form: fd }); attachment = a;
      chipBox.replaceChildren(h("div", { class: "chip" }, h("img", { class: "thumb", src: URL.createObjectURL(f), alt: "" }), h("span", { text: "Photo attached" }),
        h("button", { class: "btn quiet", type: "button", text: "Remove", onclick: () => { attachment = null; chipBox.replaceChildren(); } })));
    } catch (x) { toast(x.message, true); }
  };

  (async () => {
    await loadRail();
    if (!sid) return empty();
    try {
      const d = await api(`/chat/sessions/${sid}`);
      if (!d.messages.length) empty();
      d.messages.forEach((m) => { seen.add(m.id); lastId = m.id; if (!(m.author === "ui")) bubble(m.role, m.content, m.cards, m.author); else bubble("user", m.content); });
      if (d.session.pending_confirmation) confirmCard(d.session.pending_confirmation);
      if (d.session.handled_by === "human") bubble("assistant", "A support agent is handling this chat.", [], "system");
    } catch (x) { toast(x.message, true); navigate("#/chat"); }
  })();

  const timer = setInterval(() => { if (!document.hidden && !busy) sync(); }, 6000);
  return () => { alive = false; clearInterval(timer); };
}