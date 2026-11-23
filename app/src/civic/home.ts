/** Home: the city as a map. Every open issue is one pin; a draggable sheet (floating panel on
 * desktop) holds the numbers, category filters and the ranked list. */
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

const DELHI: [number, number] = [77.19, 28.62];
/** Sheet heights on phones: peek (numbers + filters), half, nearly full. */
const DETENTS = [0.3, 0.52, 0.9];

export function issueRow(i: IssueSummary): HTMLElement {
  const place = i.place || L("Unnamed spot", "बिना नाम की जगह");
  return h("a", { class: "issue-row", href: `#/i/${i.issueId}` },
    catBadge(i.category, i.priority),
    h("div", { class: "issue-row-main" },
      h("div", { class: "issue-row-title" }, h("b", {}, catLabel(i.category)), " · ", place),
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
  const shown = issues.filter((i) => filter === "ALL" || i.category === filter);
  pins?.clear();
  for (const i of shown) pins?.pin([i.lon, i.lat], pinFor(i));
  if (!fitted && shown.length) {
    fitted = true;
    map?.fit(shown.map((i) => [i.lon, i.lat] as [number, number]), 40);
  }
  root.querySelector(".home-list")!.replaceChildren(...(shown.length ? shown.map(issueRow)
    : [h("p", { class: "empty" }, L("No open issues here. Seen a problem? Report it.", "यहाँ कोई खुली समस्या नहीं। कुछ दिखा? रिपोर्ट करें।"))]));
  const p1 = shown.filter((i) => i.priority === "P1").length;
  const overdue = shown.filter((i) => i.overdueDays > 0).length;
  root.querySelector(".home-stats")!.replaceChildren(
    stat(String(shown.length), L("open", "खुली")),
    stat(String(p1), L("urgent", "अति आवश्यक"), "p1"),
    stat(String(overdue), L("overdue", "देर"), overdue ? "warn" : ""),
    stat(String(shown.reduce((a, i) => a + i.reports, 0)), L("reports", "रिपोर्ट")),
  );
  for (const b of root.querySelectorAll<HTMLButtonElement>(".filter-chip")) b.setAttribute("aria-pressed", String(b.dataset.cat === filter));
}

/** Drag the handle between detents; tapping it cycles them. Pointer events cover touch and mouse. */
function draggable(sheet: HTMLElement, handle: HTMLElement): void {
  let detent = 0;
  const set = (frac: number) => {
    sheet.style.setProperty("--sheet-h", `${frac * 100}%`);
    root.style.setProperty("--sheet-h", `${frac * 100}%`);
  };
  set(DETENTS[detent]);
  let startY = 0, startH = 0, moved = false;
  handle.addEventListener("pointerdown", (e) => {
    startY = e.clientY;
    startH = sheet.getBoundingClientRect().height;
    moved = false;
    sheet.classList.add("dragging");
    handle.setPointerCapture(e.pointerId);
  });
  handle.addEventListener("pointermove", (e) => {
    if (!handle.hasPointerCapture(e.pointerId)) return;
    const parent = sheet.parentElement!.getBoundingClientRect().height;
    const frac = Math.min(.95, Math.max(.18, (startH + startY - e.clientY) / parent));
    if (Math.abs(e.clientY - startY) > 6) moved = true;
    set(frac);
  });
  handle.addEventListener("pointerup", (e) => {
    sheet.classList.remove("dragging");
    const parent = sheet.parentElement!.getBoundingClientRect().height;
    const now = sheet.getBoundingClientRect().height / parent;
    detent = moved ? DETENTS.reduce((best, d, i) => (Math.abs(d - now) < Math.abs(DETENTS[best] - now) ? i : best), 0)
      : (detent + 1) % DETENTS.length;
    set(DETENTS[detent]);
    handle.releasePointerCapture(e.pointerId);
    setTimeout(() => map?.resize(), 360);
  });
  handle.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    detent = (detent + 1) % DETENTS.length;
    set(DETENTS[detent]);
  });
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
    const handle = h("div", { class: "sheet-handle", role: "button", tabindex: "0", "aria-label": L("Resize the list", "सूची का आकार बदलें") });
    const sheet = h("section", { class: "sheet", "aria-label": L("Open issues", "खुली समस्याएँ") },
      handle,
      h("div", { class: "sheet-head" },
        h("div", { class: "sheet-title" }, h("h1", {}, L("Delhi, right now", "दिल्ली, अभी")),
          h("span", { class: "meta" }, L("one pin per problem", "हर समस्या एक पिन"))),
        h("div", { class: "home-stats" }), chips),
      h("div", { class: "sheet-body" }, h("div", { class: "home-list" })));
    el.append(
      h("div", { class: "home-map", id: "home-map", role: "region", "aria-label": L("Map of open issues", "खुली समस्याओं का नक्शा") }),
      sheet,
      btn(h("span", {}, icon("locate", 20)), "secondary map-fab", nearMe, { "aria-label": L("Show issues near me", "मेरे पास की समस्याएँ") }),
    );
    draggable(sheet, handle);
    fitted = false;
    map = await createMap(el.querySelector<HTMLElement>("#home-map")!, { center: DELHI, zoom: 11, interactive: true });
    pins = map.layer();
    me = map.layer();
  }
  map?.resize();
  try {
    issues = (await civicApi.issues({ status: "open" })).issues;
  } catch (err) {
    toast(L("Could not load issues. Showing nothing rather than old data.", "समस्याएँ लोड नहीं हुईं।"), "error");
    console.warn(err);
    issues = [];
  }
  draw();
}
