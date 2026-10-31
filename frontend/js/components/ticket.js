import { h, fmtDate, label } from "../ui.js";
import { money } from "../ui.js";

const PRI = { high: "sig", medium: "warn", low: "dim" };

export function ticket(c) {
  const lvl = c.escalation_level || 1;
  const done = !["open", "pending_review"].includes(c.status);
  return h("article", { class: "ticket", "aria-label": `Complaint ${c.id}` },
    h("div", { class: "ticket-top" },
      h("span", { class: "mono", text: c.id }),
      h("span", {}, h("span", { class: `stamp ${PRI[c.priority] || "dim"}`, text: `${label(c.priority)} priority` }), " ",
        h("span", { class: "stamp dim", text: label(c.status) }))),
    h("div", {}, h("strong", { text: label(c.category) }), c.order_id ? h("span", { class: "muted" }, " on order ", h("span", { class: "mono", text: c.order_id })) : null),
    c.description ? h("div", { class: "muted", text: c.description }) : null,
    done ? (c.resolution_note ? h("div", { text: `Note: ${c.resolution_note}` }) : null) : h("div", {},
      h("div", { class: "levels", "aria-label": `Escalation level ${lvl} of 3` },
        [1, 2, 3].map((n) => h("span", { class: n <= lvl ? "on" : "", text: `L${n}` }))),
      h("div", { class: "muted", text: `With: ${c.escalation_label}. Response due ${fmtDate(c.sla_due_at, true)}` })));
}

export function costLedger(b) {
  const rows = [...b.items.map((i) => [`${i.qty} × ${i.name}`, i.line_total]),
    ["Tax", b.tax], ["Delivery charge", b.delivery_charge], ...(b.discount ? [["Discount", -b.discount]] : [])];
  return h("article", { class: "ticket", "aria-label": `Cost breakdown for ${b.order_id}` },
    h("div", { class: "ticket-top" }, h("span", { class: "mono", text: b.order_id }), h("strong", { text: "Cost breakdown" })),
    h("div", { class: "scroll-x" }, h("table", { class: "ledger-table" }, h("tbody", {},
      rows.map(([k, v]) => h("tr", {}, h("td", { text: k }), h("td", { class: "num", text: money(v, b.currency) }))),
      h("tr", {}, h("td", {}, h("strong", { text: "Total" })), h("td", { class: "num" }, h("strong", { text: money(b.total, b.currency) })))))),
    b.payment ? h("div", { class: "muted", text: `Payment ${b.payment.status} (${b.payment.provider}). Refunded so far: ${money(b.payment.amount_refunded, b.currency)}.` }) : null,
    b.refund.status !== "none" ? h("div", { text: `Refund ${b.refund.status}: ${money(b.refund.amount, b.currency)}` }) : null);
}
