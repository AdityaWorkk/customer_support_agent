import { api, fetchBlobUrl } from "../api.js";
import { h, clear, toast, fmtDate, label, statusStamp, money, fill } from "../ui.js";
import { waybill } from "../components/waybill.js";

const PRI = { high: "sig", medium: "warn", low: "dim" };

export function mount(root) {
  let tab = "complaints", timer = null;
  const body = h("div"), tabs = h("div", { class: "tabs", role: "tablist" }), stats = h("div", { class: "stats" });
  root.replaceChildren(h("div", { class: "page" }, h("div", { class: "page-head" }, h("h2", { text: "Admin desk" })), stats, tabs, body));
  const stop = () => { if (timer) clearInterval(timer); timer = null; };

  function renderTabs() {
    tabs.replaceChildren(...[["complaints", "Review queue"], ["chats", "Live chats"], ["orders", "Orders"], ["audit", "Audit log"]].map(([k, t]) =>
      h("button", { class: "tab", type: "button", role: "tab", "aria-selected": tab === k, text: t, onclick: () => { stop(); tab = k; renderTabs(); load(); } })));
  }
  async function loadStats() {
    try { const s = await api("/admin/stats");
      stats.replaceChildren(...[["open_complaints", "Open complaints"], ["pending_reviews", "Photo reviews waiting"], ["human_chats", "Chats with an agent"], ["failed_refunds", "Failed refunds"]]
        .map(([k, t]) => h("div", {}, h("b", { text: s[k] }), h("span", { text: t })))); } catch { /* ignore */ }
  }
  async function load() {
    loadStats(); clear(body).append(h("div", { class: "skeleton" }));
    try { await ({ complaints, chats, orders, audit })[tab](); } catch (x) { clear(body).append(h("p", { class: "err", text: x.message })); }
  }

  async function complaints() {
    const items = await api("/admin/complaints");
    const detail = h("div", { class: "panel" }, h("p", { class: "muted", text: "Select a complaint to review it." }));
    const table = items.length ? h("div", { class: "scroll-x" }, h("table", { class: "ledger-table" },
      h("thead", {}, h("tr", {}, ["Complaint", "Type", "Priority", "Level", "Opened"].map((t) => h("th", { text: t })))),
      h("tbody", {}, items.map((c) => h("tr", { class: "click", tabindex: 0, onclick: () => open(c.id), onkeydown: (e) => e.key === "Enter" && open(c.id) },
        h("td", { class: "mono", text: c.id }), h("td", { text: label(c.category) }),
        h("td", {}, h("span", { class: `stamp ${PRI[c.priority]}`, text: c.priority })),
        h("td", { class: "mono", text: `L${c.escalation_level}` }), h("td", { text: fmtDate(c.created_at, true) })))))) : h("p", { class: "muted", text: "Nothing waiting. New photo reviews and complaints appear here." });
    clear(body).append(h("div", { class: "split" }, table, detail));

    async function open(id) {
      const c = await api(`/admin/complaints/${id}`);
      const note = h("textarea", { "aria-label": "Note to customer", placeholder: "Note (shown to the customer)", maxlength: 500 });
      const decide = async (decision) => {
        try { await api(`/admin/complaints/${id}/decision`, { method: "POST", body: { decision, note: note.value } }); toast("Decision recorded."); load(); }
        catch (x) { toast(x.message, true); }
      };
      const img = c.attachment ? h("img", { class: "big-img", alt: "Customer's defect photo" }) : null;
      if (img) (async () => { try { img.src = c.attachment.url.startsWith("/api") ? await fetchBlobUrl(c.attachment.url) : c.attachment.url; } catch { img.replaceWith(h("p", { class: "err", text: "Photo could not be loaded." })); } })();
      const review = c.status === "pending_review";
      fill(detail, h("h3", { text: `${c.id}: ${label(c.category)}` }),
        h("p", { class: "muted", text: `${c.user.name || ""} ${c.user.email || ""}` }), h("p", { text: c.description }), img,
        c.order ? waybill(c.order) : null,
        h("hr", { class: "rule" }), note,
        h("div", { class: "actions", style: null }, review
          ? [h("button", { class: "btn primary", type: "button", text: "Approve and refund", onclick: () => decide("approve") }), h("button", { class: "btn", type: "button", text: "Reject", onclick: () => decide("reject") })]
          : [h("button", { class: "btn primary", type: "button", text: "Mark resolved", onclick: () => decide("resolve") }), h("button", { class: "btn", type: "button", text: "Reject", onclick: () => decide("reject") })]));
    }
  }

  async function chats() {
    const list = await api("/admin/sessions");
    const pane = h("div", { class: "panel" }, h("p", { class: "muted", text: "Select a chat to read it or take over." }));
    clear(body).append(h("div", { class: "split" },
      h("div", { class: "scroll-x" }, h("table", { class: "ledger-table" }, h("thead", {}, h("tr", {}, ["Customer", "Chat", "Handled by"].map((t) => h("th", { text: t })))),
        h("tbody", {}, list.map((s) => h("tr", { class: "click", tabindex: 0, onclick: () => open(s.id), onkeydown: (e) => e.key === "Enter" && open(s.id) },
          h("td", { text: s.user_email || "Unknown" }), h("td", { text: s.title }), h("td", { text: s.handled_by === "human" ? "Agent" : "Assistant" })))))), pane));

    async function open(sid) {
      stop();
      let last = null;
      const log = h("div", { class: "admin-chat", role: "log" }), input = h("textarea", { "aria-label": "Reply to customer", placeholder: "Reply as support agent", maxlength: 2000 });
      const line = (m) => h("div", { class: "msg " + (m.role === "user" ? "user" : "bot") }, h("div", { class: "who", text: m.role === "user" ? "Customer" : (m.author === "admin" ? "Agent" : m.author === "system" ? "System" : "Assistant") }), h("div", { class: "txt", text: m.content }));
      const d = await api(`/admin/sessions/${sid}`);
      d.messages.forEach((m) => { last = m.id; log.append(line(m)); });
      const takeBtn = h("button", { class: "btn", type: "button" });
      const setBtn = (human) => { takeBtn.textContent = human ? "Hand back to assistant" : "Take over chat"; takeBtn.onclick = async () => { try { await api(`/admin/sessions/${sid}/${human ? "release" : "takeover"}`, { method: "POST" }); setBtn(!human); } catch (x) { toast(x.message, true); } }; };
      setBtn(d.session.handled_by === "human");
      const send = h("button", { class: "btn primary", type: "button", text: "Send reply", onclick: async () => {
        if (!input.value.trim()) return;
        try { const m = await api(`/admin/sessions/${sid}/messages`, { method: "POST", body: { content: input.value } }); last = m.id; log.append(line(m)); input.value = ""; log.scrollTop = log.scrollHeight; }
        catch (x) { toast(x.message, true); } } });
      pane.replaceChildren(h("h3", { text: d.session.title }), log, input, h("div", { class: "actions", style: null }, send, takeBtn));
      timer = setInterval(async () => {
        const n = await api(`/admin/sessions/${sid}/messages?after=${last}`).catch(() => null);
        n?.messages.forEach((m) => { last = m.id; log.append(line(m)); log.scrollTop = log.scrollHeight; });
      }, 4000);
    }
  }

  async function orders() {
    const list = await api("/admin/orders");
    const act = async (path, ok) => { try { await api(path, { method: "POST" }); toast(ok); load(); } catch (x) { toast(x.message, true); } };
    clear(body).append(h("div", { class: "scroll-x" }, h("table", { class: "ledger-table" },
      h("thead", {}, h("tr", {}, ["Order", "Status", "Total", "Payment", "Refund", ""].map((t) => h("th", { text: t })))),
      h("tbody", {}, list.map((o) => h("tr", {}, h("td", { class: "mono", text: o.id }), h("td", {}, statusStamp(o.status)),
        h("td", { class: "num", text: money(o.total, o.currency) }), h("td", { class: "mono", text: o.payment?.provider || "" }),
        h("td", { text: o.refund.status === "none" ? "None" : label(o.refund.status) }),
        h("td", {}, ["placed", "packed", "shipped", "out_for_delivery"].includes(o.status) ? h("button", { class: "btn quiet", type: "button", text: "Advance status", onclick: () => act(`/admin/orders/${o.id}/advance`, "Status advanced.") }) : null,
          o.refund.status === "failed" ? h("button", { class: "btn quiet", type: "button", text: "Retry refund", onclick: () => act(`/admin/orders/${o.id}/retry-refund`, "Refund retried.") }) : null)))))));
  }

  async function audit() {
    const list = await api("/admin/audit");
    clear(body).append(list.length ? h("table", { class: "ledger-table" }, h("thead", {}, h("tr", {}, ["When", "Admin", "Action", "Target"].map((t) => h("th", { text: t })))),
      h("tbody", {}, list.map((a) => h("tr", {}, h("td", { text: fmtDate(a.at, true) }), h("td", { text: a.admin }), h("td", { text: label(a.action) }), h("td", { class: "mono", text: a.target }))))) : h("p", { class: "muted", text: "No admin actions yet." }));
  }

  renderTabs(); load();
  return stop;
}