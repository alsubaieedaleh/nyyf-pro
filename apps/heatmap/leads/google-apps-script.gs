/**
 * Nyyf sign-ups -> a Google Sheet you own. Free, no server.
 *
 * Setup (about 3 minutes):
 *  1. Create a Google Sheet (for example "Nyyf sign-ups").
 *  2. Extensions > Apps Script. Replace the code with this file and save.
 *  3. Deploy > New deployment > type "Web app".
 *     Execute as: Me. Who has access: Anyone. Deploy, and allow the permissions.
 *  4. Copy the web app URL (ends in /exec) into the GitHub repository variable HEATMAP_LEADS_URL
 *     (Settings > Secrets and variables > Actions > Variables), then run "Heat map deploy".
 *
 * The site posts: name, contact, role, city, interest, locale, source, consent.
 * Rows land in the "leads" tab with a timestamp. Only you (and people you share the Sheet with) can read them.
 * Report sign-ups are rows with interest "district_report" and an email in "contact".
 *
 * Report email (optional, also free):
 *  5. In the Apps Script editor pick the function setupWeeklyTrigger and press Run once (allow the Gmail permission).
 *     Every Sunday at about 9:00 it runs sendWeeklyReports: it reads the site's data/report.json and emails each
 *     subscriber the quarterly district report for their city, in Arabic or English. A city's report goes out only
 *     when that city has a new quarter, so nobody gets the same email twice. Each email has a one-click unsubscribe link (this web app's doGet).
 *     Gmail allows about 100 emails a day from a personal account (1,500 from Google Workspace).
 */
const SITE_URL = "https://alsubaieedaleh.github.io/nyyf-pro/";
const UNSUB_SHEET = "unsubscribed";
const SHEET = "leads";
const FIELDS = ["name", "contact", "role", "city", "interest", "locale", "source", "consent"];

function doPost(e) {
  const p = (e && e.parameter) || {};
  // Drop obvious junk: the form requires consent, a contact and a short name.
  if (p.consent !== "yes" || !p.contact || String(p.name || "").length > 80 || String(p.contact).length > 120) {
    return ContentService.createTextOutput("ignored");
  }
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const book = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = book.getSheetByName(SHEET) || book.insertSheet(SHEET);
    if (sheet.getLastRow() === 0) sheet.appendRow(["received_at"].concat(FIELDS));
    // A leading quote keeps phone numbers and anything starting with = as plain text.
    const row = FIELDS.map(function (f) { return "'" + String(p[f] || "").slice(0, 200); });
    sheet.appendRow([new Date()].concat(row));
  } finally {
    lock.releaseLock();
  }
  return ContentService.createTextOutput("ok");
}

function doGet(e) {
  const p = (e && e.parameter) || {};
  if (p.unsub && p.t && p.t === token_(p.unsub)) {
    const book = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = book.getSheetByName(UNSUB_SHEET) || book.insertSheet(UNSUB_SHEET);
    sheet.appendRow([new Date(), "'" + String(p.unsub).toLowerCase()]);
    return HtmlService.createHtmlOutput(
      '<div dir="rtl" style="font-family:sans-serif;padding:24px">تم إلغاء اشتراكك في التقرير الربعي.<br><span dir="ltr">You are unsubscribed from the district report.</span></div>');
  }
  return ContentService.createTextOutput("Nyyf sign-ups endpoint is running.");
}

/** Run once from the editor: checks every Sunday morning and sends the report when a city has a new quarter. */
function setupWeeklyTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(function (t) { return t.getHandlerFunction() === "sendWeeklyReports"; })
    .forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger("sendWeeklyReports").timeBased().onWeekDay(ScriptApp.WeekDay.SUNDAY).atHour(9).create();
}

function sendWeeklyReports() {
  const props = PropertiesService.getScriptProperties();
  const report = JSON.parse(UrlFetchApp.fetch(SITE_URL + "data/report.json").getContentText());
  // A report "edition" changes when any city gets a new quarter; until then nobody gets a repeat email.
  const edition = Object.keys(report.cities).sort().map(function (c) { return c + ":" + report.cities[c].quarter; }).join(",");
  if (props.getProperty("last_edition_sent") === edition) return;
  const sentFor = JSON.parse(props.getProperty("last_quarter_by_city") || "{}");
  const book = SpreadsheetApp.getActiveSpreadsheet();
  const leads = book.getSheetByName(SHEET);
  if (!leads || leads.getLastRow() < 2) return;
  const unsubSheet = book.getSheetByName(UNSUB_SHEET);
  const unsub = {};
  if (unsubSheet && unsubSheet.getLastRow() > 0) {
    unsubSheet.getRange(1, 2, unsubSheet.getLastRow(), 1).getValues().forEach(function (r) { unsub[String(r[0]).toLowerCase()] = true; });
  }
  // Latest sign-up per email wins (city and language).
  const head = leads.getRange(1, 1, 1, leads.getLastColumn()).getValues()[0];
  const col = function (name) { return head.indexOf(name); };
  const subs = {};
  leads.getRange(2, 1, leads.getLastRow() - 1, head.length).getValues().forEach(function (r) {
    const email = String(r[col("contact")]).trim().toLowerCase();
    if (r[col("interest")] !== "district_report" || email.indexOf("@") < 1) return;
    subs[email] = { city: String(r[col("city")]), locale: String(r[col("locale")]) === "en" ? "en" : "ar" };
  });
  const base = ScriptApp.getService().getUrl();
  let sent = 0;
  Object.keys(subs).forEach(function (email) {
    if (unsub[email] || MailApp.getRemainingDailyQuota() < 1) return;
    const s = subs[email];
    const city = report.cities[s.city] ? s.city : "riyadh";
    if (sentFor[city] === report.cities[city].quarter) return; // this city has no new quarter
    const link = base + "?unsub=" + encodeURIComponent(email) + "&t=" + token_(email);
    const mail = reportEmail_(report.cities[city], city, s.locale, link);
    MailApp.sendEmail({ to: email, subject: mail.subject, htmlBody: mail.html, name: "Nyyf نيّف" });
    sent++;
  });
  Object.keys(report.cities).forEach(function (c) { sentFor[c] = report.cities[c].quarter; });
  props.setProperty("last_quarter_by_city", JSON.stringify(sentFor));
  props.setProperty("last_edition_sent", edition);
  console.log("report " + edition + ": sent " + sent);
}

function reportEmail_(c, city, locale, unsubLink) {
  const ar = locale === "ar";
  const cityName = ar ? c.name_ar : c.name_en;
  const segName = { land: ["أراضي", "Land"], villa: ["فلل", "Villas"], apartment: ["شقق", "Apartments"], all: ["كل السكني", "All residential"] };
  const quarter = function (q) { return ar ? "الربع " + q.slice(-1) + " " + q.slice(0, 4) : "Q" + q.slice(-1) + " " + q.slice(0, 4); };
  const nm = function (d) { return ar ? d.name_ar : d.name_en || d.name_ar; };
  const pct = function (v) { return (v > 0 ? "+" : "") + Math.round(v * 100) + "%"; };
  const qs = function (n) { return ar ? (n === 1 ? "ربع واحد" : n === 2 ? "ربعين" : n + " أرباع") : n + (n === 1 ? " quarter" : " quarters"); };
  const list = function (title, rows, cell, type) {
    if (!rows.length) return "";
    return "<h4 style='margin:14px 0 4px'>" + title + "</h4><table style='width:100%;border-collapse:collapse'>" +
      rows.slice(0, 5).map(function (d) {
        return "<tr><td style='padding:5px 0;border-bottom:1px solid #eee'><a href='" + SITE_URL + "map.html?mode=sale&type=" + type + "#" + city + "/" + d.id +
          "' style='color:#157d79;text-decoration:none'>" + nm(d) + "</a></td><td style='padding:5px 0;border-bottom:1px solid #eee;text-align:" +
          (ar ? "left" : "right") + "'>" + cell(d) + "</td></tr>";
      }).join("") + "</table>";
  };
  const body = Object.keys(c.segments).map(function (k) {
    const s = c.segments[k];
    const type = k === "all" ? "land" : k;
    return "<h3 style='margin:22px 0 4px;color:#157d79'>" + segName[k][ar ? 0 : 1] + "</h3>" +
      "<p style='margin:0;color:#555'>" + (ar ? "صاعدة " : "Rising ") + s.rising + " · " + (ar ? "هابطة " : "falling ") + s.falling +
      (s.median_chg != null ? " · " + (ar ? "التغير الوسيط " : "median change ") + pct(s.median_chg) : "") + "</p>" +
      list(ar ? "الأكثر صعودًا" : "Biggest risers", s.risers, function (d) { return "<b style='color:#c4544a'>" + pct(d.chg) + "</b> · " + qs(d.streak); }, type) +
      list(ar ? "الأكثر هبوطًا" : "Biggest fallers", s.fallers, function (d) { return "<b style='color:#1f9e8f'>" + pct(d.chg) + "</b> · " + qs(d.streak); }, type);
  }).join("");
  const source = c.source === "rega"
    ? (ar ? "المصدر: صكوك السجل العقاري (الهيئة العامة للعقار) حسب نوع العقار." : "Source: Real Estate Registry deeds (REGA) by property type.")
    : (ar ? "المصدر: صفقات وزارة العدل، الأراضي والفلل والشقق معًا." : "Source: MOJ deals, land, villas and apartments together.");
  const html =
    "<div dir='" + (ar ? "rtl" : "ltr") + "' style='font-family:Tahoma,Arial,sans-serif;max-width:560px;margin:auto;color:#1d2827'>" +
    "<h2 style='color:#157d79;margin-bottom:4px'>" + (ar ? "تقرير نيّف الربعي · " : "Nyyf quarterly report · ") + cityName + "</h2>" +
    "<p style='color:#666;font-size:13px;margin-top:0'>" + quarter(c.from) + " – " + quarter(c.quarter) + (ar ? " مقابل " : " against ") +
    quarter(c.vs_from) + " – " + quarter(c.vs) + ". " +
    (ar ? "السهم: منذ كم ربع والحي فوق (أو تحت) العام الماضي." : "The count: quarters in a row above (or below) last year.") + "</p>" +
    body +
    "<p style='margin-top:24px'><a href='" + SITE_URL + "home.html?city=" + city + "#report' style='background:#157d79;color:#fff;padding:10px 18px;border-radius:999px;text-decoration:none'>" +
    (ar ? "التقرير كاملًا" : "Full report") + "</a></p>" +
    "<p style='color:#888;font-size:12px;margin-top:24px'>" + source + " " +
    (ar ? "تقديرات وليست أرقامًا رسمية. " : "Estimates, not official figures. ") +
    "<a href='" + unsubLink + "' style='color:#888'>" + (ar ? "إلغاء الاشتراك" : "Unsubscribe") + "</a></p></div>";
  return { subject: (ar ? "نيّف · تقرير أحياء " : "Nyyf · District report, ") + cityName + " · " + quarter(c.quarter), html: html };
}

/** Signed unsubscribe token, so a link only unsubscribes its own email. */
function token_(email) {
  const props = PropertiesService.getScriptProperties();
  let secret = props.getProperty("secret");
  if (!secret) {
    secret = Utilities.getUuid();
    props.setProperty("secret", secret);
  }
  const sig = Utilities.computeHmacSha256Signature(String(email).toLowerCase(), secret);
  return Utilities.base64EncodeWebSafe(sig).slice(0, 22);
}
