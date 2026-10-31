import { h, money, fmtDate, statusStamp, label } from "../ui.js";
import { stepper } from "./stepper.js";

export const CANCELLABLE = new Set(["placed", "packed", "shipped", "out_for_delivery"]);

export function waybill(o, { actions } = {}) {
  const ended = ["cancelled", "refunded", "cancel_requested"].includes(o.status);
  const loc = o.order_location ? [o.order_location.city, o.order_location.state].filter(Boolean).join(", ") : "Not recorded";
  return h("article", { class: "waybill", "aria-label": `Order ${o.id}` },
    h("div", { class: "wb-head" },
      h("div", {}, h("div", { class: "muted", text: "Order" }), h("div", { class: "wb-id", text: o.id })),
      statusStamp(o.status)),
    h("ul", { class: "wb-items" }, o.items.map((i) => h("li", {},
      h("span", {}, `${i.qty} × ${i.name} `, h("span", { class: "mono muted", text: i.sku })),
      h("span", { class: "mono", text: money(i.unit_price * i.qty, o.currency) })))),
    h("div", { class: "perf" }),
    h("dl", { class: "wb-meta" },
      h("div", {}, h("dt", { text: "Ordered" }), h("dd", { text: fmtDate(o.ordered_at) })),
      h("div", {}, h("dt", { text: "Ordered from" }), h("dd", { text: loc })),
      h("div", {}, h("dt", { text: "Delivering to" }), h("dd", { text: o.shipping_address || "Not recorded" })),
      h("div", {}, h("dt", { text: "Estimated delivery" }), h("dd", { text: o.status === "delivered" ? "Delivered" : fmtDate(o.estimated_delivery) }))),
    ended ? h("p", { class: "muted", text: o.status === "cancel_requested" ? "Cancellation in progress. Your refund is being processed." : `This order is ${label(o.status).toLowerCase()}.` }) : stepper(o),
    h("div", { class: "perf" }),
    h("div", { class: "wb-foot" },
      h("div", {}, h("div", { class: "muted", text: "Total paid" }), h("div", { class: "total", text: money(o.total, o.currency) })),
      actions || null));
}
