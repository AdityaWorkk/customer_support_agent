import { api, refreshSession } from "./api.js";
import { state } from "./store.js";
import { h, $ } from "./ui.js";
import * as auth from "./views/auth.js";
import * as chat from "./views/chat.js";
import * as orders from "./views/orders.js";
import * as profile from "./views/profile.js";
import * as admin from "./views/admin.js";
import * as shop from "./views/shop.js";

const app = document.getElementById("app");
const VIEWS = { shop, chat, orders, profile, admin };
let cleanup = null;

export function navigate(hash) { if (location.hash === hash) route(); else location.hash = hash; }

async function logout() {
  try { await api("/auth/logout", { method: "POST", auth: false }); } catch { /* ignore */ }
  state.user = state.token = null; navigate("#/login");
}

function shell(active) {
  const content = h("main", { id: "content" });
  const links = [["shop", "Shop"], ["chat", "Chat"], ["orders", "Orders"], ["profile", "Profile"], ...(state.user.role === "admin" ? [["admin", "Admin"]] : [])];
  app.replaceChildren(h("div", { class: "shell" },
    h("header", { class: "top" }, h("a", { class: "brand", href: "#/chat", text: state.config.app_name }),
      h("nav", { class: "nav", "aria-label": "Main" }, links.map(([k, t]) => h("a", { href: `#/${k}`, "aria-current": k === active ? "page" : null, text: t }))),
      h("button", { class: "btn quiet", type: "button", text: "Sign out", onclick: logout })), content));
  return content;
}

function route() {
  cleanup?.(); cleanup = null;
  const [name, ...params] = location.hash.replace(/^#\/?/, "").split("/");
  if (!state.user) {
    if (name !== "login") history.replaceState(null, "", "#/login");
    return void (cleanup = auth.mount(app, { onAuthed: () => navigate("#/chat") }));
  }
  if (!name || name === "login") return navigate("#/chat");
  const view = VIEWS[name];
  if (!view || (name === "admin" && state.user.role !== "admin")) return navigate("#/chat");
  document.title = `${name[0].toUpperCase() + name.slice(1)} | ${state.config.app_name}`;
  cleanup = view.mount(shell(name), { params, navigate, onLogout: logout });
}

window.addEventListener("hashchange", route);

(async () => {
  try { state.config = await (await fetch("/api/v1/config")).json(); } catch { /* defaults */ }
  app.replaceChildren(h("p", { class: "muted", style: null, text: "Loading…", role: "status" }));
  await refreshSession();
  route();
})();
