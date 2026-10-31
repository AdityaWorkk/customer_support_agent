import { h } from "../ui.js";

const STEPS = [["placed", "Placed"], ["packed", "Packed"], ["shipped", "Shipped"], ["out_for_delivery", "Out for delivery"], ["delivered", "Delivered"]];

export function stepper(order) {
  const base = order.status === "cancel_requested" ? order.cancel_from_status : order.status;
  const idx = STEPS.findIndex(([k]) => k === base);
  const ol = h("ol", { class: "stepper", "aria-label": "Delivery progress" },
    STEPS.map(([k, name], i) => h("li", { class: i < idx ? "done" : i === idx ? "done now" : "", "aria-current": i === idx ? "step" : null, text: name })));
  ol.style.setProperty("--p", idx <= 0 ? 0 : idx / (STEPS.length - 1));
  return ol;
}
