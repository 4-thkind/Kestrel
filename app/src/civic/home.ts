/** Neighborhood dashboard. The map and list share category and text filters. */
import { createMap, type Layer, type MapView } from "../map/mapview.ts";
import { civicApi, type Category, type IssueSummary } from "./api.ts";
import { CATEGORIES, L, ago, btn, catBadge, catLabel, h, icon, priorityChip, toast, wfLabel } from "./ui.ts";

let map: MapView | undefined;
let pins: Layer | undefined;
let me: Layer | undefined;
let filter: Category | "ALL" = "ALL";
let issues: IssueSummary[] = [];
let root: HTMLElement;
let fitted = false;
let search = "";
let loadFailed = false;

const DELHI: [number, number] = [77.19, 28.62];
export function issueRow(i: IssueSummary): HTMLElement {
  const place = i.place || L("Unnamed spot", "बिना नाम की जगह");
  return h("a", { class: "issue-row", href: `#/i/${i.issueId}` },
    catBadge(i.category, i.priority),
    h("div", { class: "issue-row-main" },
      h("div", { class: "issue-row-title" }, h("b", {}, catLabel(i.category))),
      h("div", { class: "issue-place" }, icon("pin", 12), place),
      h("div", { class: "issue-row-meta" },
        priorityChip(i.priority, i.score),
        h("span", { class: `wf wf-${i.workflowState.toLowerCase()}` }, wfLabel(i.workflowState)),
        h("span", { class: "meta" }, `${i.reports} ${L("reports", "रिपोर्ट")}`),
        i.overdueDays > 0 ? h("span", { class: "overdue" }, `${i.overdueDays}${L("d overdue", " दिन देर")}`) : null,
        i.blocksRoute ? h("span", { class: "routes-flag", title: L("Routes avoid this", "रास्ते इससे बचते हैं") }, icon("route", 14)) : null,
      ),
    ),
    h("span", { class: "issue-row-age" }, ago(i.updatedAt)),
  );
}

function pinFor(i: IssueSummary): HTMLElement {
  const el = h("a", { class: `map-pin prio-bg-${i.priority.toLowerCase()}`, href: `#/i/${i.issueId}`,
    "aria-label": `${catLabel(i.category)} · ${i.place ?? ""} · ${i.priority}` }, icon(i.category, 16));
  if (i.priority === "P1") el.classList.add("pulse");
  return el;
}

const stat = (n: string, label: string, cls = "") => h("div", { class: `stat ${cls}` }, h("b", {}, n), h("span", {}, label));

function draw(): void {
  const shown = issues.filter((i) => (filter === "ALL" || i.category === filter)
    && `${catLabel(i.category)} ${i.place ?? ""} ${wfLabel(i.workflowState)}`.toLocaleLowerCase().includes(search));
  pins?.clear();
  for (const i of shown) pins?.pin([i.lon, i.lat], pinFor(i));
  if (!fitted && shown.length) {
    fitted = true;
    map?.fit(shown.map((i) => [i.lon, i.lat] as [number, number]), 40);
  }
  root.querySelector(".home-list")!.replaceChildren(...(shown.length ? shown.map(issueRow)
    : [h("div", { class: "empty" }, icon(loadFailed ? "map" : "check", 28),
      h("b", {}, loadFailed ? L("We couldn’t load the issues", "समस्याएँ लोड नहीं हुईं") : L("No issues to show", "कोई समस्या नहीं मिली")),
      h("p", {}, loadFailed ? L("Check your connection and try again.", "कनेक्शन जाँचें और फिर कोशिश करें।") : L("Try another search or category, or report something you’ve spotted.", "दूसरी श्रेणी चुनें या नई समस्या रिपोर्ट करें।")),
      loadFailed ? btn(L("Try again", "फिर कोशिश करें"), "secondary small", () => { void showHome(root); }) : null)]));
  const p1 = issues.filter((i) => i.priority === "P1").length;
  const overdue = issues.filter((i) => i.overdueDays > 0).length;
  root.querySelector(".home-stats")!.replaceChildren(
    stat(loadFailed ? "—" : String(issues.length), L("Open issues", "खुली समस्याएँ")),
    stat(loadFailed ? "—" : String(p1), L("Need urgent attention", "तुरंत ध्यान चाहिए"), "p1"),
    stat(loadFailed ? "—" : String(overdue), L("Past their due date", "समय सीमा पार"), overdue ? "warn" : ""),
    stat(loadFailed ? "—" : String(issues.reduce((a, i) => a + i.reports, 0)), L("Community reports", "सामुदायिक रिपोर्ट")),
  );
  root.querySelector(".issue-count")!.textContent = loadFailed ? L("Unavailable", "अनुपलब्ध") : L(`${shown.length} issues`, `${shown.length} समस्याएँ`);
  root.querySelector(".map-status")!.textContent = loadFailed ? L("Issues unavailable", "समस्याएँ अनुपलब्ध") : L("Community reported", "समुदाय द्वारा रिपोर्ट");
  for (const b of root.querySelectorAll<HTMLButtonElement>(".filter-chip")) b.setAttribute("aria-pressed", String(b.dataset.cat === filter));
}

function nearMe(): void {
  if (!navigator.geolocation) return toast(L("No GPS on this device.", "इस डिवाइस में GPS नहीं।"), "warn");
  navigator.geolocation.getCurrentPosition((p) => {
    const at: [number, number] = [p.coords.longitude, p.coords.latitude];
    me?.clear();
    me?.pin(at, h("span", { class: "map-pin me" }, icon("locate", 16)));
    map?.view(at, 15);
  }, () => toast(L("Location blocked or unavailable.", "लोकेशन नहीं मिली।"), "warn"), { timeout: 10_000, maximumAge: 60_000 });
}

export async function showHome(el: HTMLElement): Promise<void> {
  root = el;
  if (!el.dataset.built) {
    el.dataset.built = "1";
    const chips = h("div", { class: "filters", role: "group", "aria-label": L("Filter by category", "श्रेणी से छाँटें") },
      ...(["ALL", ...CATEGORIES] as const).map((c) => {
        const b = h("button", { type: "button", class: "filter-chip", "data-cat": c }, c === "ALL" ? L("All", "सभी") : catLabel(c));
        if (c !== "ALL") b.prepend(icon(c, 16));
        b.addEventListener("click", () => {
          filter = c;
          fitted = false;
          draw();
        });
        return b;
      }));
    const input = h("input", { type: "search", class: "issue-search", placeholder: L("Search issues or places…", "समस्या या जगह खोजें…"), "aria-label": L("Search issues or places", "समस्या या जगह खोजें") }) as HTMLInputElement;
    input.value = search;
    input.addEventListener("input", () => { search = input.value.trim().toLocaleLowerCase(); fitted = false; draw(); });
    el.append(
      h("header", { class: "dashboard-heading" },
        h("div", {}, h("div", { class: "eyebrow" }, L("YOUR NEIGHBORHOOD, CONNECTED", "आपका जुड़ा हुआ पड़ोस")),
          h("h1", {}, L("Better streets start with us.", "बेहतर सड़कें हमसे शुरू होती हैं।")),
          h("p", { class: "muted" }, L("Spot an issue. Help your neighbors. Follow the fix.", "समस्या बताएँ। पड़ोसियों की मदद करें। सुधार देखें।"))),
        h("a", { class: "primary", href: "#/report" }, icon("plus", 18), L("Report an issue", "समस्या रिपोर्ट करें"))),
      h("div", { class: "home-stats", "aria-label": L("City overview", "शहर का सारांश") }),
      h("section", { class: "explore-section", "aria-label": L("Explore local issues", "स्थानीय समस्याएँ देखें") },
        h("div", { class: "explore-heading" },
          h("div", {}, h("h2", {}, L("Around your neighborhood", "आपके पड़ोस में")), h("p", { class: "meta" }, L("A little awareness goes a long way.", "थोड़ी जागरूकता बड़ा बदलाव लाती है।"))),
          h("span", { class: "city-label" }, icon("pin", 16), L("New Delhi, India", "नई दिल्ली, भारत"))),
        h("div", { class: "explore-toolbar" }, chips, h("label", { class: "search-wrap" }, icon("locate", 17), input)),
        h("div", { class: "explore-grid" },
          h("section", { class: "map-panel", "aria-label": L("Neighborhood map", "पड़ोस का नक्शा") },
            h("div", { class: "home-map", id: "home-map", role: "region", "aria-label": L("Map of open issues", "खुली समस्याओं का नक्शा") }),
            h("span", { class: "map-status" }, L("Loading issues…", "समस्याएँ लोड हो रही हैं…")),
            btn(h("span", {}, icon("locate", 18), L("Near me", "मेरे पास")), "secondary map-fab", nearMe, { "aria-label": L("Show issues near me", "मेरे पास की समस्याएँ") }),
            h("div", { class: "map-legend" },
              h("span", { class: "legend-urgent" }, L("Urgent", "अति आवश्यक")),
              h("span", { class: "legend-moderate" }, L("Moderate", "मध्यम")),
              h("span", { class: "legend-low" }, L("Low priority", "कम प्राथमिकता")))),
          h("section", { class: "list-panel", "aria-label": L("Open issues", "खुली समस्याएँ") },
            h("div", { class: "list-heading" }, h("h2", {}, L("On the radar", "नज़र में")), h("span", { class: "issue-count", "aria-live": "polite" })),
            h("div", { class: "home-list" }, h("p", { class: "empty" }, L("Loading issues…", "समस्याएँ लोड हो रही हैं…"))))),
      ),
      h("aside", { class: "community-banner" },
        h("span", { class: "community-icon" }, icon("shield", 28)),
        h("div", {}, h("h2", {}, L("Your everyday route. A little safer.", "आपका रोज़ का सफ़र। थोड़ा सुरक्षित।")), h("p", {}, L("Plan a ride that takes reported road hazards into account.", "सड़क की रिपोर्ट की गई समस्याओं को ध्यान में रखकर सफ़र चुनें।"))),
        h("a", { href: "#/navigate", class: "secondary" }, L("Plan a safer ride", "सुरक्षित सफ़र चुनें"), icon("arrow", 18))),
      h("footer", { class: "dashboard-footer" }, L("Small reports. Real change. A better city, together.", "छोटी रिपोर्ट। असली बदलाव। साथ मिलकर बेहतर शहर।"), h("a", { href: "#/wards" }, L("Explore ward scorecards", "वार्ड स्कोरकार्ड देखें"), " ↗")),
    );
    fitted = false;
    map = await createMap(el.querySelector<HTMLElement>("#home-map")!, { center: DELHI, zoom: 11, interactive: true });
    pins = map.layer();
    me = map.layer();
  }
  map?.resize();
  try {
    loadFailed = false;
    issues = (await civicApi.issues({ status: "open" })).issues;
  } catch (err) {
    toast(L("Could not load issues. Showing nothing rather than old data.", "समस्याएँ लोड नहीं हुईं।"), "error");
    console.warn(err);
    loadFailed = true;
    issues = [];
  }
  draw();
}
