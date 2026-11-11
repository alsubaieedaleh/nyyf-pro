import { STRINGS, type Locale } from "./i18n";
import CITY_LIST from "../../../data/pipelines/cities.json";

export const LEADS_URL: string | undefined = import.meta.env.VITE_LEADS_URL || undefined;
const BEACON_TOKEN: string | undefined = import.meta.env.VITE_CF_BEACON_TOKEN || undefined;

// The cities the pipeline tries (data/pipelines/cities.json). The maps and the market page show only the ones
// with enough data (meta.json / market.json); sign-up forms offer them all.
export const CITY_SLUGS: string[] = CITY_LIST.map((c) => c.slug);
export const CITY_NAMES: Record<string, { ar: string; en: string }> = Object.fromEntries(
  CITY_LIST.map((c) => [c.slug, { ar: c.ar, en: c.en }]),
);

export function getLocale(): Locale {
  try {
    const saved = localStorage.getItem("nyyf-locale");
    if (saved === "ar" || saved === "en") return saved;
  } catch {
    /* storage blocked */
  }
  return "ar"; // Arabic first: the audience is Saudi brokers, buyers and owners
}

export function saveLocale(l: Locale) {
  try {
    localStorage.setItem("nyyf-locale", l);
  } catch {
    /* storage blocked */
  }
}

export function setDocLocale(l: Locale) {
  document.documentElement.lang = l;
  document.documentElement.dir = l === "ar" ? "rtl" : "ltr";
}

export const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

export function esc(s: string) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

export function toast(msg: string) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  document.body.append(el);
  setTimeout(() => el.classList.add("show"), 10);
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 300);
  }, 2200);
}

/** Cookie-free visitor counts (Cloudflare Web Analytics), only when a token is configured. */
export function analytics() {
  if (!BEACON_TOKEN) return;
  const s = document.createElement("script");
  s.defer = true;
  s.src = "https://static.cloudflareinsights.com/beacon.min.js";
  s.dataset.cfBeacon = JSON.stringify({ token: BEACON_TOKEN });
  document.head.append(s);
}

/** Site header for the landing and home pages. */
export function renderNav(el: HTMLElement, locale: Locale, current: "landing" | "home") {
  const s = STRINGS[locale];
  el.innerHTML = `
    <a class="nav-brand" href="./"><img src="./icon.png" alt="" width="30" height="30" /><span>${s.brand}</span></a>
    <nav class="nav-links">
      <a href="./home.html"${current === "home" ? ' aria-current="page"' : ""}>${s.navHome}</a>
      <a href="./map.html?mode=sale">${s.navSale}</a>
      <a href="./map.html?mode=rent">${s.navRent}</a>
    </nav>
    <div class="nav-end">
      <a class="pill small primary" href="./#join">${s.navJoin}</a>
      <button class="pill small" id="lang-btn">${s.lang}</button>
    </div>`;
}

// ---------- Sign-up form ----------

const PHONE = /^(\+?966|0)?5\d{8}$/;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function renderLeadForm(el: HTMLElement, locale: Locale, source: string) {
  const s = STRINGS[locale];
  const opt = (o: Record<string, string>) => Object.entries(o).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  el.innerHTML = `
    <form class="lead" novalidate>
      <div class="row">
        <label><span>${s.fName}</span><input name="name" autocomplete="name" maxlength="80" required /></label>
        <label><span>${s.fContact}</span><input name="contact" autocomplete="tel" inputmode="email" maxlength="120" required dir="ltr" /></label>
      </div>
      <div class="row">
        <label><span>${s.fRole}</span><select name="role" required><option value="" disabled selected>—</option>${opt(s.roles)}</select></label>
        <label><span>${s.fCity}</span><select name="city" required><option value="" disabled selected>—</option>${CITY_SLUGS.map((c) => `<option value="${c}">${esc(CITY_NAMES[c][locale])}</option>`).join("")}<option value="other">${esc(s.roles.other)}</option></select></label>
      </div>
      <label><span>${s.fInterest}</span><select name="interest"><option value="" selected>—</option>${opt(s.interests)}</select></label>
      <input class="hp" name="website" tabindex="-1" autocomplete="off" aria-hidden="true" />
      <label class="check"><input type="checkbox" name="consent" required /><span>${s.fConsent}</span></label>
      <button class="pill primary big" type="submit">${s.fSubmit}</button>
      <p class="form-msg" role="status" aria-live="polite"></p>
      <p class="fine">${s.privacy}</p>
    </form>`;
  const form = el.querySelector("form")!;
  const msg = form.querySelector<HTMLElement>(".form-msg")!;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    if (fd.get("website")) return; // bot
    const contact = String(fd.get("contact") || "").replace(/[\s-]/g, "");
    if (!fd.get("name") || !fd.get("role") || !fd.get("city") || !fd.get("consent")) {
      form.reportValidity();
      return;
    }
    if (!PHONE.test(contact) && !EMAIL.test(contact)) {
      msg.textContent = s.fInvalid;
      msg.className = "form-msg err";
      return;
    }
    if (!LEADS_URL) {
      msg.textContent = s.fSoon;
      msg.className = "form-msg err";
      return;
    }
    const btn = form.querySelector<HTMLButtonElement>("button[type=submit]")!;
    btn.disabled = true;
    btn.textContent = s.fSending;
    const body = new URLSearchParams({
      name: String(fd.get("name")).slice(0, 80),
      contact,
      role: String(fd.get("role")),
      city: String(fd.get("city")),
      interest: String(fd.get("interest") || ""),
      locale,
      source,
      consent: "yes",
    });
    try {
      // Google Apps Script web apps do not answer CORS preflights, so the post is "no-cors":
      // the browser sends it but cannot read the reply. A network failure still throws.
      await fetch(LEADS_URL, { method: "POST", mode: "no-cors", body });
      form.reset();
      msg.textContent = s.fThanks;
      msg.className = "form-msg ok";
      try {
        localStorage.setItem("nyyf-joined", "1");
      } catch {
        /* storage blocked */
      }
    } catch {
      msg.textContent = s.fError;
      msg.className = "form-msg err";
    } finally {
      btn.disabled = false;
      btn.textContent = s.fSubmit;
    }
  });
}

/** Email-only sign-up for the quarterly district report. */
export function renderReportForm(el: HTMLElement, locale: Locale, city: string, cities: string[] = CITY_SLUGS) {
  const s = STRINGS[locale];
  el.innerHTML = `
    <form class="lead report" novalidate>
      <div class="row">
        <label><span>${s.rEmail}</span><input name="contact" type="email" autocomplete="email" maxlength="120" required dir="ltr" /></label>
        <label><span>${s.fCity}</span><select name="city">${cities.map(
          (c) => `<option value="${c}"${c === city ? " selected" : ""}>${esc(CITY_NAMES[c][locale])}</option>`,
        ).join("")}</select></label>
      </div>
      <input class="hp" name="website" tabindex="-1" autocomplete="off" aria-hidden="true" />
      <label class="check"><input type="checkbox" name="consent" required /><span>${s.rConsent}</span></label>
      <button class="pill primary big" type="submit">${s.rSubmit}</button>
      <p class="form-msg" role="status" aria-live="polite"></p>
    </form>`;
  const form = el.querySelector("form")!;
  const msg = form.querySelector<HTMLElement>(".form-msg")!;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    if (fd.get("website")) return;
    const email = String(fd.get("contact") || "").trim();
    if (!EMAIL.test(email)) {
      msg.textContent = s.rInvalid;
      msg.className = "form-msg err";
      return;
    }
    if (!fd.get("consent")) {
      form.reportValidity();
      return;
    }
    if (!LEADS_URL) {
      msg.textContent = s.fSoon;
      msg.className = "form-msg err";
      return;
    }
    const btn = form.querySelector<HTMLButtonElement>("button[type=submit]")!;
    btn.disabled = true;
    const body = new URLSearchParams({
      name: "",
      contact: email,
      role: "",
      city: String(fd.get("city")),
      interest: "district_report",
      locale,
      source: "report",
      consent: "yes",
    });
    try {
      await fetch(LEADS_URL, { method: "POST", mode: "no-cors", body });
      form.reset();
      msg.textContent = s.rThanks;
      msg.className = "form-msg ok";
    } catch {
      msg.textContent = s.fError;
      msg.className = "form-msg err";
    } finally {
      btn.disabled = false;
    }
  });
}
