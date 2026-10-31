import { api } from "../api.js";
import { h, clear, stagger, toast, money, label } from "../ui.js";
import { waybill, CANCELLABLE } from "../components/waybill.js";
import { ticket, costLedger } from "../components/ticket.js";

const CATEGORIES = ["late_delivery", "wrong_item", "staff_misconduct", "website_performance", "billing_issue", "other"];

export function mount(root) {
  let tab = "orders";
  const body = h("div");
  const tabs = h("div", { class: "tabs", role: "tablist" });
  root.replaceChildren(h("div", { class: "page" }, h("div", { class: "page-head" }, h("h2", { text: "Your orders" })), tabs, body));

  function renderTabs() {
    tabs.replaceChildren(...[["orders", "Orders"], ["complaints", "Complaints"]].map(([k, t]) =>
      h("button", { class: "tab", type: "button", role: "tab", "aria-selected": tab === k, text: t, onclick: () => { tab = k; renderTabs(); load(); } })));
  }

  async function load() {
    clear(body).append(h("div", { class: "skeleton", "aria-label": "Loading" }));
    try { tab === "orders" ? await showOrders() : await showComplaints(); }
    catch (x) { clear(body).append(h("p", { class: "err", text: x.message })); }
  }

  async function showOrders() {
    const orders = await api("/orders");
    clear(body);
    if (!orders.length) return body.append(h("p", { class: "muted", text: "You have no orders yet." }));
    const list = h("div", { class: "cards" });
    for (const o of orders) {
      const slot = h("div", { class: "cards" });
      const actions = h("div", { class: "actions", style: null });
      const bd = h("button", { class: "btn quiet", type: "button", text: "Cost breakdown", onclick: async () => {
        try { slot.replaceChildren(costLedger(await api(`/orders/${o.id}/cost-breakdown`))); } catch (x) { toast(x.message, true); } } });
      actions.append(bd);
      if (CANCELLABLE.has(o.status)) actions.append(h("button", { class: "btn", type: "button", text: "Cancel order", onclick: () => cancelFlow(o, slot) }));
      list.append(h("div", { class: "cards" }, waybill(o, { actions }), slot));
    }
    body.append(list); stagger(list);
  }

  async function cancelFlow(o, slot) {
    try {
      const p = await api(`/orders/${o.id}/cancel-preview`);
      if (!p.eligible) return toast(p.reason, true);
      const go = h("button", { class: "btn primary", type: "button", text: "Confirm cancellation" });
      const keep = h("button", { class: "btn", type: "button", text: "Keep order", onclick: () => slot.replaceChildren() });
      go.onclick = async () => {
        go.disabled = keep.disabled = true;
        try {
          const r = await api(`/orders/${o.id}/cancel`, { method: "POST", body: { confirm: true } });
          toast(r.refund_status === "failed" ? "Cancelled, but the refund needs support to retry." : "Order cancelled. Your refund is on its way.");
          load();
        } catch (x) { toast(x.message, true); go.disabled = keep.disabled = false; }
      };
      slot.replaceChildren(h("div", { class: "confirm" }, h("h3", { text: `Cancel ${o.id}?` }),
        h("div", { class: "row" }, h("span", { text: "Order total" }), h("span", { class: "mono", text: money(p.total, p.currency) })),
        p.retained_delivery_fee ? h("div", { class: "row" }, h("span", { text: "Delivery charge kept" }), h("span", { class: "mono", text: `− ${money(p.retained_delivery_fee, p.currency)}` })) : null,
        h("div", { class: "row" }, h("strong", { text: "You get back" }), h("strong", { class: "mono", text: money(p.refund_amount, p.currency) })),
        h("div", { class: "actions" }, go, keep)));
    } catch (x) { toast(x.message, true); }
  }

  async function showComplaints() {
    const [cs, orders] = await Promise.all([api("/complaints"), api("/orders")]);
    const err = h("p", { class: "err", role: "alert" });
    const form = h("form", { class: "panel", novalidate: true },
      h("h3", { text: "Raise a complaint" }),
      h("p", { class: "muted", text: "For a damaged or defective product, attach a photo in the chat instead so a person can review it." }),
      h("div", { class: "field" }, h("label", { for: "c-cat", text: "What happened?" }),
        h("select", { id: "c-cat", name: "category" }, CATEGORIES.map((c) => h("option", { value: c, text: label(c) })))),
      h("div", { class: "field" }, h("label", { for: "c-ord", text: "Related order (optional)" }),
        h("select", { id: "c-ord", name: "order_id" }, h("option", { value: "", text: "None" }), orders.map((o) => h("option", { value: o.id, text: o.id })))),
      h("div", { class: "field" }, h("label", { for: "c-desc", text: "Details" }), h("textarea", { id: "c-desc", name: "description", minlength: 5, maxlength: 2000, required: true })),
      err, h("button", { class: "btn primary", type: "submit", text: "Submit complaint" }));
    form.onsubmit = async (e) => {
      e.preventDefault(); err.textContent = "";
      const fd = Object.fromEntries(new FormData(form));
      try { await api("/complaints", { method: "POST", body: { category: fd.category, description: fd.description, order_id: fd.order_id || null } }); toast("Complaint submitted."); load(); }
      catch (x) { err.textContent = x.message; }
    };
    clear(body).append(h("div", { class: "split" }, h("div", { class: "cards" }, cs.length ? cs.map(ticket) : h("p", { class: "muted", text: "No complaints yet." })), form));
  }

  renderTabs(); load();
  return () => {};
}
