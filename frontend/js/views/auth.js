import { api } from "../api.js";
import { state } from "../store.js";
import { h, stagger, fill } from "../ui.js";

const SAMPLE = [["ORD-20931", "Brass desk lamp", "Out for delivery"], ["ORD-20877", "Stoneware mug set", "Packed"],
  ["ORD-20812", "Trail backpack", "Delivered"], ["ORD-20790", "Copper kettle", "Shipped"], ["ORD-20744", "Wireless headphones", "Delivered"]];

const G_LOGO = "data:image/svg+xml;utf8," + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">' +
  '<path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>' +
  '<path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>' +
  '<path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>' +
  '<path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>');

function loadGoogle() {
  return new Promise((resolve, reject) => {
    if (window.google?.accounts) return resolve();
    const s = h("script", { src: "https://accounts.google.com/gsi/client", async: true });
    s.onload = resolve; s.onerror = reject;
    document.head.append(s);
  });
}

export function mount(root, { onAuthed }) {
  let mode = "login";
  const err = h("p", { class: "err", role: "alert" });
  const form = h("form", { novalidate: true });
  const tabs = h("div", { class: "tabs", role: "tablist" });
  const gbtn = h("button", { class: "google-btn", type: "button", disabled: true },
    h("img", { src: G_LOGO, alt: "", width: 18, height: 18 }), h("span", { text: "Continue with Google" }));

  async function submit(e) {
    e.preventDefault(); err.textContent = "";
    const fd = Object.fromEntries(new FormData(form));
    const btn = form.querySelector("button[type=submit]"); btn.disabled = true;
    try {
      const d = await api(mode === "login" ? "/auth/login" : "/auth/register", { method: "POST", auth: false,
        body: mode === "login" ? { email: fd.email, password: fd.password } : { email: fd.email, password: fd.password, name: fd.name } });
      state.token = d.access_token; state.user = d.user; onAuthed();
    } catch (x) { err.textContent = x.message; btn.disabled = false; }
  }

  function renderForm() {
    fill(tabs, [["login", "Sign in"], ["register", "Create account"]].map(([k, t]) =>
      h("button", { class: "tab", type: "button", role: "tab", "aria-selected": mode === k, text: t, onclick: () => { mode = k; err.textContent = ""; renderForm(); } })));
    const field = (id, lbl, type, extra = {}) => h("div", { class: "field" }, h("label", { for: id, text: lbl }), h("input", { id, name: id, type, required: true, ...extra }));
    fill(form,
      mode === "register" ? field("name", "Full name", "text", { autocomplete: "name", maxlength: 80 }) : null,
      field("email", "Email", "email", { autocomplete: "email" }),
      field("password", "Password", "password", { autocomplete: mode === "login" ? "current-password" : "new-password", minlength: mode === "register" ? 8 : null }),
      mode === "register" ? h("p", { class: "muted", text: "At least 8 characters." }) : null,
      err, h("button", { class: "btn primary", type: "submit", text: mode === "login" ? "Sign in" : "Create account" }));
  }
  form.addEventListener("submit", submit);
  renderForm();

  const hasGoogle = !!state.config.google_client_id;
  root.replaceChildren(h("main", { class: "auth" },
    h("section", { class: "auth-art", "aria-hidden": "true" },
      h("h1", { text: "Ask about your order. Get a straight answer." }),
      h("ul", { class: "ledger" }, SAMPLE.map(([id, item, st]) => h("li", {}, h("span", { class: "mono", text: id }), h("span", { text: item }), h("span", { class: "mono muted", text: st }))))),
    h("section", { class: "auth-form" },
      h("h2", { text: "Welcome back" }),
      h("p", { class: "muted", text: "Track orders, cancel before they arrive, or report a problem." }),
      hasGoogle ? gbtn : null, hasGoogle ? h("div", { class: "divider", text: "or use your email" }) : null, tabs, form)));
  stagger(root.querySelector(".ledger"));

  if (hasGoogle) {
    loadGoogle().then(() => {
      const client = google.accounts.oauth2.initTokenClient({
        client_id: state.config.google_client_id,
        scope: "openid email profile",
        callback: async (resp) => {
          if (resp.error || !resp.access_token) { err.textContent = "Google sign-in was cancelled or failed."; gbtn.disabled = false; return; }
          try {
            const d = await api("/auth/google/token", { method: "POST", auth: false, body: { access_token: resp.access_token } });
            state.token = d.access_token; state.user = d.user; onAuthed();
          } catch (x) { err.textContent = x.message; gbtn.disabled = false; }
        },
        error_callback: () => { gbtn.disabled = false; },
      });
      gbtn.disabled = false;
      gbtn.onclick = () => { err.textContent = ""; gbtn.disabled = true; client.requestAccessToken({ prompt: "select_account" }); };
    }).catch(() => { err.textContent = "Google sign-in couldn't load. Use email instead."; });
  }
  return () => {};
}