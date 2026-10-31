import { api } from "../api.js";
import { state } from "../store.js";
import { h, toast } from "../ui.js";

export function mount(root, { onLogout }) {
  const u = state.user;
  const err = h("p", { class: "err", role: "alert" }), perr = h("p", { class: "err", role: "alert" });
  const f = (id, lbl, val, extra = {}) => h("div", { class: "field" }, h("label", { for: id, text: lbl }), h("input", { id, name: id, value: val ?? "", ...extra }));

  const profile = h("form", { class: "panel", novalidate: true },
    h("h3", { text: "Your details" }),
    f("email", "Email", u.email, { disabled: true }),
    f("name", "Full name", u.name, { maxlength: 80, required: true }),
    f("phone", "Phone", u.phone, { maxlength: 20, autocomplete: "tel" }),
    f("address", "Delivery address", u.address, { maxlength: 300, autocomplete: "street-address" }),
    err, h("button", { class: "btn primary", type: "submit", text: "Save changes" }));
  profile.onsubmit = async (e) => {
    e.preventDefault(); err.textContent = "";
    const fd = Object.fromEntries(new FormData(profile));
    try { state.user = await api("/auth/me", { method: "PATCH", body: { name: fd.name, phone: fd.phone, address: fd.address } }); toast("Changes saved."); }
    catch (x) { err.textContent = x.message; }
  };

  const pw = h("form", { class: "panel", novalidate: true },
    h("h3", { text: u.has_password ? "Change password" : "Set a password" }),
    u.google_linked ? h("p", { class: "muted", text: "Your Google account is linked. A password lets you sign in with email too." }) : null,
    u.has_password ? f("current_password", "Current password", "", { type: "password", autocomplete: "current-password" }) : null,
    f("new_password", "New password", "", { type: "password", minlength: 8, autocomplete: "new-password", required: true }),
    perr, h("button", { class: "btn", type: "submit", text: "Update password" }));
  pw.onsubmit = async (e) => {
    e.preventDefault(); perr.textContent = "";
    const fd = Object.fromEntries(new FormData(pw));
    try { await api("/auth/change-password", { method: "POST", body: { current_password: fd.current_password || null, new_password: fd.new_password } }); toast("Password updated. Sign in again."); onLogout(); }
    catch (x) { perr.textContent = x.message; }
  };

  root.replaceChildren(h("div", { class: "page" }, h("div", { class: "page-head" }, h("h2", { text: "Profile" })),
    h("div", { class: "split" }, profile, pw)));
  return () => {};
}
