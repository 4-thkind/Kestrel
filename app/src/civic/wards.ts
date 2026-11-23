/** Public ward scorecards: computed only from data Kestrel can defend (citizen-confirmed fixes, reopens, delays). */
import { civicApi, type Scorecard, type Ward } from "./api.ts";
import { L, catLabel, h, toast } from "./ui.ts";
import { issueRow } from "./home.ts";

const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);

function metric(value: string, label: string, hint: string, cls = ""): HTMLElement {
  return h("div", { class: `metric ${cls}`, title: hint }, h("b", {}, value), h("span", {}, label));
}

/** Letter grade from the rank score: easy to read at a glance, still computed from defensible numbers. */
function grade(s: Scorecard): string {
  const v = rankScore(s);
  return v >= 80 ? "A" : v >= 60 ? "B" : v >= 40 ? "C" : v >= 20 ? "D" : "F";
}

function card(w: Ward, rank: number): HTMLElement {
  const s = w.scorecard;
  const g = grade(s);
  return h("a", { class: "ward-card card", href: `#/wards/${w.id}` },
    h("div", { class: "ward-top" }, h("span", { class: `grade grade-${g.toLowerCase()}`, title: L("Ward grade", "वार्ड ग्रेड") }, g),
      h("div", {}, h("h2", {}, L(w.name, w.nameHi)), h("p", { class: "meta" }, `${w.agency} · ${w.id}`)),
      h("span", { class: "rank" }, `#${rank}`)),
    h("div", { class: "meter", title: L("Citizen-confirmed fixes", "नागरिक-पुष्ट मरम्मत") },
      h("i", { style: `width:${Math.round((s.confirmedFixRate ?? 0) * 100)}%` })),
    h("div", { class: "metrics" },
      metric(String(s.openIssues), L("open", "खुली"), ""),
      metric(String(s.openByPriority.P1), L("urgent", "अति आवश्यक"), "", s.openByPriority.P1 ? "p1" : ""),
      metric(String(s.overdue), L("overdue", "देर"), "", s.overdue ? "warn" : ""),
      metric(pct(s.confirmedFixRate), L("fixes confirmed", "पुष्ट मरम्मत"),
        L("Citizen-confirmed fixes ÷ (confirmed + unconfirmed closures + reopens)", "नागरिक-पुष्ट / कुल")),
      metric(s.medianDaysToResolve === null ? "—" : `${s.medianDaysToResolve}d`, L("median fix time", "औसत समय"), "")));
}

/** Higher is better: confirmed fixes, few urgent and overdue issues. */
function rankScore(s: Scorecard): number {
  return (s.confirmedFixRate ?? 0.5) * 100 - s.openByPriority.P1 * 8 - s.overdue * 5 - s.reopens * 4;
}

export async function showWards(el: HTMLElement, wardId?: string): Promise<void> {
  let wards: Ward[];
  try {
    wards = (await civicApi.wards()).wards;
  } catch {
    toast(L("Could not load wards.", "वार्ड लोड नहीं हुए।"), "error");
    return;
  }
  if (!wardId) {
    const ranked = [...wards].sort((a, b) => rankScore(b.scorecard) - rankScore(a.scorecard));
    el.replaceChildren(h("div", { class: "page" },
      h("header", { class: "page-head" }, h("h1", {}, L("Ward scorecards", "वार्ड स्कोरकार्ड")),
        h("p", { class: "muted" }, L("A fix counts only when citizens confirm it. Reopens and overdue issues count against a ward.",
          "मरम्मत तभी गिनी जाती है जब नागरिक पुष्टि करें। दोबारा खुलना और देरी वार्ड के ख़िलाफ़ गिने जाते हैं।"))),
      h("div", { class: "ward-grid" }, ...ranked.map((w, i) => card(w, i + 1))),
      h("p", { class: "fineprint" }, L("Sample ward areas around real localities, not official boundaries. Demo data is synthetic.",
        "असली इलाकों के आसपास नमूना क्षेत्र, आधिकारिक सीमा नहीं। डेमो डेटा कृत्रिम है।"))));
    return;
  }
  const w = wards.find((x) => x.id === wardId);
  if (!w) return void el.replaceChildren(h("div", { class: "page" }, h("h1", {}, L("Unknown ward", "अज्ञात वार्ड"))));
  const s = w.scorecard;
  const open = (await civicApi.issues({ status: "open", ward: wardId })).issues;
  const cats = Object.entries(s.byCategory).filter(([, n]) => n > 0);
  el.replaceChildren(h("div", { class: "page" },
    h("a", { href: "#/wards", class: "back link" }, "← ", L("All wards", "सभी वार्ड")),
    h("header", { class: "page-head" }, h("p", { class: "eyebrow" }, `${w.agency} · ${w.id}`), h("h1", {}, L(w.name, w.nameHi))),
    h("div", { class: "metrics big" },
      metric(String(s.openIssues), L("open issues", "खुली समस्याएँ"), ""),
      metric(String(s.openByPriority.P1), L("urgent P1", "P1"), "", s.openByPriority.P1 ? "p1" : ""),
      metric(String(s.overdue), L("past deadline", "समय सीमा पार"), "", s.overdue ? "warn" : ""),
      metric(pct(s.confirmedFixRate), L("fixes confirmed by citizens", "नागरिक-पुष्ट मरम्मत"), ""),
      metric(String(s.reopens), L("reopened after 'fixed'", "'ठीक' के बाद दोबारा खुली"), "", s.reopens ? "warn" : ""),
      metric(s.medianDaysToResolve === null ? "—" : `${s.medianDaysToResolve} d`, L("median days to resolve", "हल होने में औसत दिन"), "")),
    cats.length ? h("div", { class: "tags" }, ...cats.map(([c, n]) => h("span", { class: "tag" }, `${catLabel(c as never)} ${n}`))) : null,
    h("h2", {}, L("Open issues, most urgent first", "खुली समस्याएँ, सबसे ज़रूरी पहले")),
    h("div", { class: "home-list" }, ...open.map(issueRow)),
    h("a", { class: "secondary", href: `#/officer/${w.id}` }, L("Open the ward officer console", "वार्ड अधिकारी कंसोल खोलें"))));
}
