/** Kestrel civic shell: tab bar + hash router. Routes:
 *  #/ issues map · #/report[?cat=X] · #/i/<id> · #/wards[/<id>] · #/officer[/<ward>] · #/navigate */
import { api } from "../flood/api.ts";
import { getLang, setLang } from "../flood/i18n.ts";
import type { Category } from "./api.ts";
import { showHome } from "./home.ts";
import { setIssueClientMode, showIssue } from "./issue.ts";
import { showOfficer } from "./officer.ts";
import { pendingReports, setClientMode, showReport } from "./report.ts";
import { L, h, icon } from "./ui.ts";
import { showWards } from "./wards.ts";

type View = "home" | "report" | "issue" | "wards" | "officer";
const TABS: { view: View | "navigate"; href: string; en: string; hi: string; icon: Parameters<typeof icon>[0] }[] = [
  { view: "home", href: "#/", en: "Overview", hi: "समस्याएँ", icon: "map" },
  { view: "wards", href: "#/wards", en: "Ward scorecards", hi: "वार्ड", icon: "chart" },
  { view: "report", href: "#/report", en: "Report an issue", hi: "रिपोर्ट", icon: "plus" },
  { view: "navigate", href: "#/navigate", en: "Safer routes", hi: "सफ़र", icon: "route" },
  { view: "officer", href: "#/officer", en: "Officer workspace", hi: "अधिकारी", icon: "shield" },
];

let openNavigate: () => void = () => {};
let showCivic: () => void = () => {};

function views(): Record<View, HTMLElement> {
  return Object.fromEntries((["home", "report", "issue", "wards", "officer"] as View[])
    .map((v) => [v, document.getElementById("v-" + v)!])) as Record<View, HTMLElement>;
}

function renderChrome(active: string): void {
  const nav = document.getElementById("c-tabs")!;
  nav.replaceChildren(...TABS.map((t) => h("a", { href: t.href, class: `c-tab ${t.view === "report" ? "c-tab-report" : ""}`,
    "aria-current": t.view === active ? "page" : "false", title: L(t.en, t.hi) }, icon(t.icon, 22), h("span", {}, L(t.en, t.hi)))));
  document.getElementById("c-lang")!.textContent = getLang() === "hi" ? "EN" : "हिं";
}

async function route(): Promise<void> {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, query] = raw.split("?");
  const parts = path.split("/").filter(Boolean);
  const head = parts[0] ?? "";
  if (head === "navigate") {
    openNavigate();
    return;
  }
  showCivic();
  const v = views();
  const view: View = head === "i" ? "issue" : head === "report" ? "report" : head === "wards" ? "wards" : head === "officer" ? "officer" : "home";
  for (const [name, el] of Object.entries(v)) el.hidden = name !== view;
  document.getElementById("screen-civic")!.dataset.view = view;
  renderChrome(view === "issue" ? "home" : view);
  window.scrollTo(0, 0);
  if (view === "home") await showHome(v.home);
  else if (view === "report") await showReport(v.report, (new URLSearchParams(query).get("cat") as Category | null) ?? undefined);
  else if (view === "issue") await showIssue(v.issue, parts[1] ?? "");
  else if (view === "wards") await showWards(v.wards, parts[1]);
  else await showOfficer(v.officer, parts[1] ?? "");
  const main = document.querySelector<HTMLElement>(".c-main");
  if (main) main.scrollTop = 0;
}

async function badge(): Promise<void> {
  const n = await pendingReports().catch(() => 0);
  const el = document.getElementById("c-pending")!;
  el.hidden = n === 0;
  el.textContent = L(`${n} waiting to send`, `${n} भेजना बाकी`);
}

export async function initCivic(hooks: { openNavigate: () => void; showCivic: () => void }): Promise<void> {
  openNavigate = hooks.openNavigate;
  showCivic = hooks.showCivic;
  document.getElementById("c-lang")!.addEventListener("click", () => {
    setLang(getLang() === "hi" ? "en" : "hi");
    for (const el of Object.values(views())) {
      el.replaceChildren();
      delete el.dataset.built;
    }
    void route();
  });
  try {
    const status = await api.status();
    setClientMode(status.clientMode);
    setIssueClientMode(status.clientMode);
    const mode = document.getElementById("c-mode")!;
    mode.textContent = status.provenance === "SYNTHETIC_DEMO" ? L("Demo · synthetic data", "डेमो · कृत्रिम डेटा") : L("Pilot", "पायलट");
  } catch {
    document.getElementById("c-mode")!.textContent = L("Offline", "ऑफ़लाइन");
  }
  addEventListener("hashchange", () => void route());
  addEventListener("kestrel:outbox", () => void badge());
  setInterval(() => void badge(), 15_000);
  void badge();
  await route();
}
