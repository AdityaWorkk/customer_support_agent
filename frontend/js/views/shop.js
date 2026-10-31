import { api } from "../api.js";
import { state } from "../store.js";
import { h, clear, stagger, toast, money } from "../ui.js";
import { waybill } from "../components/waybill.js";

const TONES = ["tone-1", "tone-2", "tone-3", "tone-4", "tone-5"];

export function mount(root, { navigate }) {
  let products = [], cart = null, filter = "All", mode = "cart", idem = null;
  const grid = h("div", { class: "product-grid" });
  const chips = h("div", { class: "chips", role: "group", "aria-label": "Filter by category" });
  const cartBox = h("aside", { class: "cart panel", id: "cart", "aria-label": "Your cart" });
  const bar = h("button", { class: "cart-bar", type: "button", onclick: () => cartBox.scrollIntoView({ behavior: "smooth" }) });

  root.replaceChildren(h("div", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, h("h2", { text: "Shop" }),
      h("p", { class: "muted", text: "A demo catalogue. Checkout uses a test payment, so no real money moves." }))),
    h("div", { class: "shop" }, h("section", {}, chips, grid), cartBox), bar));

  const inCart = (sku) => cart?.items.find((i) => i.sku === sku)?.qty ?? 0;
  const guard = async (fn) => { try { return await fn(); } catch (x) { toast(x.message, true); refreshCart(); } };

  async function refreshCart() { try { setCart(await api("/shop/cart")); } catch { /* keep last */ } }
  function setCart(c) { cart = c; renderCart(); renderProducts(); }

  function renderChips() {
    const cats = ["All", ...new Set(products.map((p) => p.category))];
    chips.replaceChildren(...cats.map((c) => h("button", { class: "chip-btn", type: "button", "aria-pressed": c === filter, text: c,
      onclick: () => { filter = c; renderChips(); renderProducts(); } })));
  }

  function renderProducts() {
    const list = products.filter((p) => filter === "All" || p.category === filter);
    const cats = [...new Set(products.map((p) => p.category))];
    grid.replaceChildren(...list.map((p) => {
      const q = inCart(p.sku), out = p.stock === 0, maxed = q >= Math.min(p.stock, 10);
      return h("article", { class: "product" },
        h("div", { class: `plate ${TONES[cats.indexOf(p.category) % TONES.length]}`, "aria-hidden": "true" },
          h("span", { class: "plate-cat", text: p.category }), h("span", { class: "mono", text: p.sku })),
        h("div", { class: "product-body" },
          h("h3", { text: p.name }), h("p", { class: "muted", text: p.description }),
          h("div", { class: "product-foot" },
            h("span", { class: "price", text: money(p.price) }),
            h("span", { class: out ? "stamp dim" : p.stock <= 5 ? "stamp warn" : "muted", text: out ? "Sold out" : p.stock <= 5 ? `${p.stock} left` : "" })),
          h("button", { class: "btn" + (q ? "" : " primary"), type: "button", disabled: out || maxed,
            text: out ? "Sold out" : maxed ? "Max in cart" : q ? `Add another (${q} in cart)` : "Add to cart",
            onclick: () => guard(async () => { setCart(await api("/shop/cart/items", { method: "POST", body: { sku: p.sku, qty: 1 } })); }) })));
    }));
  }

  function line(i) {
    const set = (qty) => guard(async () => setCart(await api(`/shop/cart/items/${i.sku}`, { method: "PUT", body: { qty } })));
    return h("li", { class: "cart-line" },
      h("div", {}, h("div", { class: "cart-name", text: i.name }), h("div", { class: "mono muted", text: `${money(i.unit_price)} each` }),
        i.in_stock ? null : h("div", { class: "err", text: `Only ${i.stock} left. Lower the quantity.` })),
      h("div", { class: "cart-right" }, h("div", { class: "mono", text: money(i.line_total) }),
        h("div", { class: "qty", role: "group", "aria-label": `Quantity of ${i.name}` },
          h("button", { type: "button", "aria-label": `Decrease quantity of ${i.name}`, disabled: i.qty <= 1, text: "−", onclick: () => set(i.qty - 1) }),
          h("output", { "aria-live": "polite", text: i.qty }),
          h("button", { type: "button", "aria-label": `Increase quantity of ${i.name}`, disabled: i.qty >= Math.min(i.stock, 10), text: "+", onclick: () => set(i.qty + 1) })),
        h("button", { class: "btn quiet", type: "button", text: "Remove", "aria-label": `Remove ${i.name} from cart`,
          onclick: () => guard(async () => setCart(await api(`/shop/cart/items/${i.sku}`, { method: "DELETE" }))) })));
  }

  function totals() {
    const need = cart.delivery_charge > 0 ? cart.free_delivery_over - cart.subtotal : 0;
    return h("div", {},
      need > 0 ? h("p", { class: "muted", text: `Add ${money(need)} more for free delivery.` }) : null,
      h("dl", { class: "sum" },
        h("dt", { text: "Subtotal" }), h("dd", { class: "mono", text: money(cart.subtotal) }),
        h("dt", { text: "Tax (18%)" }), h("dd", { class: "mono", text: money(cart.tax) }),
        h("dt", { text: "Delivery" }), h("dd", { class: "mono", text: cart.delivery_charge ? money(cart.delivery_charge) : "Free" }),
        h("dt", { class: "sum-total", text: "Total" }), h("dd", { class: "mono sum-total", text: money(cart.total) })));
  }

  function renderCart() {
    bar.replaceChildren(h("span", { text: `Cart (${cart.count})` }), h("span", { class: "mono", text: money(cart.total) }));
    bar.classList.toggle("show", cart.count > 0 && mode === "cart");
    if (mode === "done") return;
    if (!cart.items.length) {
      mode = "cart";
      return cartBox.replaceChildren(h("h3", { text: "Your cart" }), h("p", { class: "muted", text: "Nothing here yet. Add something from the catalogue." }));
    }
    const blocked = cart.items.some((i) => !i.in_stock);
    if (mode === "checkout") return cartBox.replaceChildren(checkoutForm(blocked));
    cartBox.replaceChildren(h("h3", { text: `Your cart (${cart.count})` }), h("ul", { class: "cart-lines" }, cart.items.map(line)), totals(),
      h("div", { class: "actions" },
        h("button", { class: "btn primary", type: "button", text: "Checkout", disabled: blocked, onclick: () => { mode = "checkout"; idem = crypto.randomUUID(); renderCart(); } }),
        h("button", { class: "btn quiet", type: "button", text: "Clear cart", onclick: () => guard(async () => setCart(await api("/shop/cart", { method: "DELETE" }))) })));
  }

  function checkoutForm(blocked) {
    const err = h("p", { class: "err", role: "alert" });
    const f = (id, lbl, extra = {}) => h("div", { class: "field" }, h("label", { for: `co-${id}`, text: lbl }), h("input", { id: `co-${id}`, name: id, required: true, ...extra }));
    const pay = h("button", { class: "btn primary", type: "submit", text: `Pay ${money(cart.total)}`, disabled: blocked });
    const form = h("form", { novalidate: true },
      h("h3", { text: "Delivery details" }),
      f("address", "Address", { value: state.user.address || "", autocomplete: "street-address", maxlength: 200 }),
      f("city", "City", { autocomplete: "address-level2", maxlength: 60 }),
      f("state", "State", { autocomplete: "address-level1", maxlength: 60 }),
      f("pincode", "PIN code", { inputmode: "numeric", pattern: "[0-9]{6}", maxlength: 6, autocomplete: "postal-code" }),
      totals(), h("p", { class: "muted", text: "Test payment only. No real money is charged." }), err,
      h("div", { class: "actions" }, pay, h("button", { class: "btn quiet", type: "button", text: "Back to cart", onclick: () => { mode = "cart"; renderCart(); } })));
    form.onsubmit = async (e) => {
      e.preventDefault(); err.textContent = "";
      const fd = Object.fromEntries(new FormData(form));
      if (!/^\d{6}$/.test(fd.pincode || "")) return void (err.textContent = "Enter a 6-digit PIN code.");
      pay.disabled = true; pay.textContent = "Processing payment…";
      try {
        const order = await api("/shop/checkout", { method: "POST", body: { ...fd, idempotency_key: idem } });
        mode = "done"; done(order); cart = await api("/shop/cart"); renderProducts(); bar.classList.remove("show");
        products = await api("/shop/products"); renderProducts();
      } catch (x) { err.textContent = x.message; pay.disabled = false; pay.textContent = `Pay ${money(cart.total)}`; if (x.status === 409) refreshCart(); }
    };
    return form;
  }

  function done(order) {
    cartBox.replaceChildren(h("h3", { text: "Order placed" }), h("p", { class: "muted", text: `Thanks. We've started on ${order.id}. Ask the assistant for updates any time.` }),
      waybill(order),
      h("div", { class: "actions" },
        h("button", { class: "btn primary", type: "button", text: "Track in chat", onclick: () => navigate("#/chat") }),
        h("button", { class: "btn", type: "button", text: "View orders", onclick: () => navigate("#/orders") }),
        h("button", { class: "btn quiet", type: "button", text: "Keep shopping", onclick: () => { mode = "cart"; renderCart(); } })));
  }

  (async () => {
    grid.append(h("div", { class: "skeleton" }));
    try {
      [products, cart] = await Promise.all([api("/shop/products"), api("/shop/cart")]);
      renderChips(); renderCart(); renderProducts(); stagger(grid);
    } catch (x) { clear(grid).append(h("p", { class: "err", text: x.message })); }
  })();
  return () => {};
}
