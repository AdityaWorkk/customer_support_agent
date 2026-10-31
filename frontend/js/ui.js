/** Tiny DOM helpers. Everything user- or model-supplied goes through textContent, never innerHTML. */
export function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else el.setAttribute(k, v === true ? (k.startsWith("aria-") ? "true" : "") : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

export function fill(el, ...kids) {
  el.replaceChildren(...kids.flat(Infinity).filter((k) => k != null && k !== false)
    .map((k) => (k instanceof Node ? k : document.createTextNode(String(k)))));
  return el;
}

export const $ = (sel, root = document) => root.querySelector(sel);

export function clear(el) { el.replaceChildren(); return el; }

export function stagger(container) {
  [...container.children].forEach((c, i) => { c.classList.add("reveal"); c.style.setProperty("--i", i); });
}

export function toast(message, bad = false) {
  const t = h("div", { class: "toast" + (bad ? " bad" : ""), text: message });
  document.getElementById("toasts").append(t);
  setTimeout(() => t.remove(), 4800);
}

const SYMBOL = { INR: "₹", USD: "$", EUR: "€" };
export function money(minor, cur = "INR") {
  return `${SYMBOL[cur] ?? cur + " "}${(minor / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function fmtDate(iso, withTime = false) {
  if (!iso) return "Not available";
  const d = new Date(iso);
  return d.toLocaleString("en-IN", withTime ? { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" } : { day: "numeric", month: "short", year: "numeric" });
}

export const label = (s) => String(s || "").replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());

/** Safe mini-markdown: paragraphs, **bold**, "- " lists. Builds DOM nodes only. */
export function renderText(el, text) {
  el.replaceChildren();
  const inline = (parent, line) => {
    line.split(/(\*\*[^*]+\*\*)/g).forEach((part) => {
      if (part.startsWith("**") && part.endsWith("**") && part.length > 4) parent.append(h("strong", { text: part.slice(2, -2) }));
      else if (part) parent.append(document.createTextNode(part));
    });
  };
  for (const block of text.trim().split(/\n{2,}/)) {
    const lines = block.split("\n");
    if (lines.every((l) => /^\s*[-*]\s+/.test(l))) {
      const ul = h("ul");
      lines.forEach((l) => { const li = h("li"); inline(li, l.replace(/^\s*[-*]\s+/, "")); ul.append(li); });
      el.append(ul);
    } else {
      const p = h("p");
      lines.forEach((l, i) => { if (i) p.append(h("br")); inline(p, l); });
      el.append(p);
    }
  }
}

export function statusStamp(status) {
  const cls = { delivered: "ok", cancelled: "dim", refunded: "dim", cancel_requested: "warn", out_for_delivery: "sig" }[status] || "sig";
  return h("span", { class: `stamp ${cls}`, text: label(status) });
}