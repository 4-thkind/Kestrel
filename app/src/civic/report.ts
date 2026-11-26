/** Report an issue in four steps: what, where, photo and details, review ("is it one of these?").
 * Reports go through the durable outbox, so a weak network never loses one. */
import type { ObservationRequest, ObservationResult } from "../flood/contracts.ts";
import { IdbStorage, MemoryStorage, Outbox, type OutboxStorage } from "../flood/queue.ts";
import { getLang } from "../flood/i18n.ts";
import { createMap, type Layer, type MapView } from "../map/mapview.ts";
import { loadImage, read, type Reading } from "./vision.ts";
import { civicApi, type Category, type Detail, type IssueSummary, type ReportBody, type WriteResult } from "./api.ts";
import {
  CATEGORIES, DETAIL_LABEL, L, btn, catBadge, catLabel, citizenId, compressPhoto, h, icon, kids, likelihood, newCitizenId, priorityChip, toast, wfLabel,
} from "./ui.ts";

const DETAILS_FOR: Record<Category, Detail[]> = {
  POTHOLE: ["deep", "wide", "major_road", "near_school", "near_hospital"],
  WATERLOGGING: ["vehicles_stuck", "major_road", "near_school", "near_hospital"],
  OPEN_MANHOLE: ["near_school", "near_hospital", "major_road", "night_hazard"],
  BLOCKED_ROAD: ["major_road", "vehicles_stuck"],
  GARBAGE_DUMP: ["near_school", "near_hospital"],
  STREETLIGHT_OUT: ["night_hazard", "major_road", "near_school"],
  OTHER: ["major_road", "near_school", "near_hospital"],
};

interface Form {
  category?: Category;
  lat?: number;
  lon?: number;
  accuracyM?: number;
  place: string;
  text: string;
  details: Set<Detail>;
  photo?: { contentType: "image/jpeg"; data: string; preview: string };
  issueId?: string;
  hint: string;
  vision?: Reading | "loading" | "failed";
}

let f: Form = { place: "", text: "", details: new Set(), hint: "" };
let step = 0;
let root: HTMLElement;
let map: MapView | undefined;
let marker: Layer | undefined;
let outbox: Outbox | undefined;
let clientMode = "LOCAL_DEMO";
let nearby: IssueSummary[] = [];
let result: { r?: WriteResult; queued: boolean } | undefined;

export function setClientMode(mode: string): void {
  clientMode = mode;
}

async function getOutbox(): Promise<Outbox> {
  if (outbox) return outbox;
  let storage: OutboxStorage;
  try {
    storage = new IdbStorage("kestrel-reports", "outbox");
    await storage.all();
  } catch {
    storage = new MemoryStorage();
  }
  // same outbox as the water reporter; civic bodies carry the same eventId/schemaVersion contract
  outbox = new Outbox(storage, (r) => civicApi.report(r.body as unknown as ReportBody, r.contributor) as unknown as Promise<ObservationResult>);
  // the shell's "waiting to send" badge listens for this; refresh it once the queue has actually changed
  const flushed = (reconnected: boolean) => void outbox?.flush(reconnected).finally(() => dispatchEvent(new Event("kestrel:outbox")));
  addEventListener("online", () => flushed(true));
  setInterval(() => flushed(false), 15_000);   // retries after server errors; backoff still applies
  return outbox;
}

export async function pendingReports(): Promise<number> {
  return (await (await getOutbox()).pending()).length;
}

const ready = (): boolean => [!!f.category, f.lat !== undefined, true, true][step];

// ------------------------------------------------------------------ actions
function setLocation(lat: number, lon: number, accuracyM?: number): void {
  f.lat = lat;
  f.lon = lon;
  f.accuracyM = accuracyM;
  marker?.clear();
  marker?.pin([lon, lat], h("span", { class: "map-pin me" }, icon("pin", 16)));
  map?.view([lon, lat], 17);
  const status = root.querySelector(".loc-status");
  if (status) status.textContent = accuracyM
    ? L(`Located within about ${Math.round(accuracyM)} m. Tap the map to adjust.`, `लगभग ${Math.round(accuracyM)} मीटर तक सही। नक्शे पर टैप करके बदलें।`)
    : L("Pin set. Tap the map to adjust.", "पिन लगा। बदलने के लिए नक्शे पर टैप करें।");
  syncNav();
}

function locate(): void {
  const status = root.querySelector(".loc-status");
  if (!navigator.geolocation) {
    if (status) status.textContent = L("No GPS on this device. Tap the map where the problem is.", "GPS नहीं है। नक्शे पर जगह टैप करें।");
    return;
  }
  if (status) status.textContent = L("Finding you…", "आपकी जगह ढूँढ रहे हैं…");
  navigator.geolocation.getCurrentPosition(
    (p) => setLocation(+p.coords.latitude.toFixed(6), +p.coords.longitude.toFixed(6), p.coords.accuracy),
    () => status && (status.textContent = L("Location blocked or unavailable. Tap the map where the problem is.", "लोकेशन नहीं मिली। नक्शे पर जगह टैप करें।")),
    { enableHighAccuracy: true, timeout: 12_000, maximumAge: 30_000 },
  );
}

async function loadNearby(): Promise<void> {
  nearby = [];
  if (f.category && f.lat !== undefined) {
    try {
      nearby = (await civicApi.issues({ status: "open", category: f.category, near: `${f.lat},${f.lon}` })).issues;
    } catch {
      /* offline: the server still fuses duplicates when the report arrives */
    }
  }
  if (f.issueId && !nearby.some((i) => i.issueId === f.issueId)) f.issueId = undefined;
  if (step === 3) render();
}

function listen(): void {
  type Rec = new () => { lang: string; interimResults: boolean; onresult: (e: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => void; onend: () => void; start(): void };
  const w = window as unknown as { SpeechRecognition?: Rec; webkitSpeechRecognition?: Rec };
  const R = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  if (!R) return toast(L("Voice input is not supported in this browser. Please type.", "इस ब्राउज़र में आवाज़ नहीं। कृपया लिखें।"), "warn");
  const rec = new R();
  rec.lang = getLang() === "hi" ? "hi-IN" : "en-IN";
  rec.interimResults = false;
  const mic = root.querySelector<HTMLButtonElement>(".mic")!;
  mic.classList.add("listening");
  rec.onresult = (e) => {
    f.text = (f.text ? f.text + " " : "") + e.results[0][0].transcript;
    root.querySelector<HTMLTextAreaElement>("#rep-say")!.value = f.text;
    void understand();
  };
  rec.onend = () => mic.classList.remove("listening");
  rec.start();
}

async function understand(): Promise<void> {
  if (f.text.trim().length < 3) return;
  f.hint = L("Reading your report…", "आपकी रिपोर्ट पढ़ रहे हैं…");
  render();
  try {
    const d = await civicApi.draft(f.text, citizenId());
    const u = d.understanding;
    if (u?.method === "covexcode" && u.place && !f.place.trim()) f.place = u.place;
    if (d.suggestedCategory) {
      f.category = d.suggestedCategory;
      for (const det of d.suggestedDetails) if (DETAILS_FOR[d.suggestedCategory].includes(det)) f.details.add(det);
      f.hint = L("We understood: ", "हमने समझा: ") + catLabel(d.suggestedCategory) +
        (d.suggestedDetails.length ? " · " + d.suggestedDetails.map((x) => L(...DETAIL_LABEL[x] as [string, string])).join(", ") : "") +
        L(". Change it if that's wrong.", "। गलत हो तो बदलें।") +
        (u?.method === "covexcode" && (u.summaryEn || u.summaryHi) ? `
${L(u.summaryEn ?? "", u.summaryHi ?? u.summaryEn ?? "")}` : "");
    } else {
      f.hint = L("Couldn't tell the problem type from that. Pick one below.", "प्रकार समझ नहीं आया। नीचे चुनें।");
    }
  } catch {
    f.hint = L("Offline: pick the problem type below.", "ऑफ़लाइन: नीचे प्रकार चुनें।");
  }
  render();
}


async function submit(): Promise<void> {
  if (!f.category || f.lat === undefined || f.lon === undefined) return;
  const body: ReportBody = {
    schemaVersion: "1.0", eventId: crypto.randomUUID(), category: f.category, observedAt: new Date().toISOString(),
    location: { lat: f.lat, lon: f.lon, accuracyM: f.accuracyM ?? null }, clientMode,
    ...(f.text.trim() ? { description: f.text.trim().slice(0, 1000) } : {}),
    ...(f.details.size ? { details: [...f.details] } : {}),
    ...(f.photo ? { photo: { contentType: f.photo.contentType, data: f.photo.data } } : {}),
    ...(f.issueId ? { issueId: f.issueId } : {}),
    ...(f.place.trim() ? { place: f.place.trim().slice(0, 120) } : {}),
  };
  const send = root.querySelector<HTMLButtonElement>(".wiz-next");
  if (send) send.disabled = true;
  try {
    const box = await getOutbox();
    await box.add(body as unknown as ObservationRequest, citizenId());
    const mine = (await box.flush()).find((o) => o.eventId === body.eventId);
    if (mine?.kind === "rejected") {
      toast(L("The server refused this report: ", "सर्वर ने रिपोर्ट नहीं ली: ") + mine.code, "error");
      if (send) send.disabled = false;
      return;
    }
    result = { r: mine ? (mine.result as unknown as WriteResult) : undefined, queued: !mine };
    dispatchEvent(new Event("kestrel:outbox"));
    render();
    focusStep();
  } catch (err) {
    toast(String(err), "error");
    if (send) send.disabled = false;
  }
}

function restart(): void {
  f = { place: "", text: "", details: new Set(), hint: "", lat: f.lat, lon: f.lon, accuracyM: f.accuracyM };
  step = 0;
  result = undefined;
  render();
  focusStep();
}

// ------------------------------------------------------------------ rendering
/** Announce a new step and reveal its heading after the previous form was scrolled. */
function focusStep(): void {
  const main = root.closest<HTMLElement>(".c-main");
  if (main) main.scrollTop = 0;
  const heading = root.querySelector<HTMLElement>(".wiz-step h1");
  heading?.setAttribute("tabindex", "-1");
  heading?.focus({ preventScroll: true });
}

function syncNav(): void {
  const next = root.querySelector<HTMLButtonElement>(".wiz-next");
  if (next) next.disabled = !ready();
}

function stepWhat(): HTMLElement {
  const say = h("textarea", { id: "rep-say", rows: "2", maxlength: "1000",
    placeholder: L("Say it in your words: \"flyover ke neeche bada gaddha hai\"", "अपने शब्दों में: \"गली में कूड़े का ढेर है\"") }) as HTMLTextAreaElement;
  say.value = f.text;
  say.addEventListener("input", () => (f.text = say.value));
  say.addEventListener("change", () => void understand());
  return h("div", { class: "wiz-step" },
    h("div", {}, h("p", { class: "eyebrow" }, L("Step 1 of 4", "चरण 1 / 4")), h("h1", {}, L("What's the problem?", "समस्या क्या है?"))),
    h("div", { class: "say-row" }, say, btn(icon("mic", 24), "mic", listen, { "aria-label": L("Speak", "बोलें") })),
    h("p", { class: "understood", "aria-live": "polite" }, f.hint),
    h("div", { class: "cat-grid", role: "group", "aria-label": L("Problem type", "समस्या का प्रकार") },
      ...CATEGORIES.map((c) => btn(h("span", {}, icon(c, 32), h("span", {}, catLabel(c))), "cat-tile", () => {
        f.category = c;
        f.details = new Set([...f.details].filter((d) => DETAILS_FOR[c].includes(d)));
        render();
      }, { "aria-pressed": String(f.category === c) }))));
}

function stepWhere(): HTMLElement {
  const place = h("input", { id: "rep-place", maxlength: "120",
    placeholder: L("Landmark (optional): near Moolchand flyover", "पहचान (वैकल्पिक): मूलचंद फ्लाईओवर के पास") }) as HTMLInputElement;
  place.value = f.place;
  place.addEventListener("input", () => (f.place = place.value));
  const mapBox = h("div", { class: "rep-map", id: "rep-map" });
  setTimeout(async () => {
    map = await createMap(mapBox, { center: f.lon !== undefined ? [f.lon, f.lat!] : [77.21, 28.62], zoom: f.lon !== undefined ? 17 : 12, interactive: true });
    marker = map.layer();
    map.onClick(([lon, lat]) => setLocation(+lat.toFixed(6), +lon.toFixed(6)));
    if (f.lat !== undefined) setLocation(f.lat, f.lon!, f.accuracyM);
    else locate();
  });
  return h("div", { class: "wiz-step" },
    h("div", {}, h("p", { class: "eyebrow" }, L("Step 2 of 4", "चरण 2 / 4")), h("h1", {}, L("Where is it?", "कहाँ है?"))),
    mapBox,
    h("div", { class: "loc-row" }, btn(h("span", {}, icon("locate", 18), L("Use my location", "मेरी जगह")), "secondary small", locate),
      h("span", { class: "loc-status muted", "aria-live": "polite" })),
    place);
}

/** Kestrel Vision reads the photo on the phone; the citizen's own choices always win. */
async function look(preview: string): Promise<void> {
  try {
    const r = await read(await loadImage(preview));
    if (f.photo?.preview !== preview) return;   // photo changed while the model ran
    f.vision = r;
    if (r.preselect && !f.category && r.guess.category) f.category = r.guess.category as Category;
  } catch (err) {
    console.warn("[vision]", err);
    f.vision = "failed";
  }
  if (step === 2) render();
}

const VISION_LABEL: Record<string, [string, string]> = {
  pothole: ["Pothole", "गड्ढा"], waterlogging: ["Waterlogging", "जलभराव"], open_manhole: ["Open manhole", "खुला मैनहोल"],
  blocked_road: ["Blocked road", "रास्ता बंद"], garbage: ["Garbage", "कूड़ा"], manhole_cover: ["Closed manhole cover", "बंद मैनहोल ढक्कन"],
  road_ok: ["Normal road", "सामान्य सड़क"], not_street: ["Not a street photo", "सड़क की फ़ोटो नहीं"],
};

function visionCard(): HTMLElement | null {
  const v = f.vision;
  if (!v || v === "failed") return null;
  if (v === "loading") return h("div", { class: "vision-card" }, h("span", { class: "vision-dot" }), L("Kestrel Vision is looking at your photo…", "Kestrel Vision फ़ोटो देख रहा है…"));
  const top = v.guess.ranked.slice(0, 3);
  const notes: (HTMLElement | null)[] = [];
  if (v.guess.key === "not_street") notes.push(h("p", { class: "vision-warn" }, L("This doesn't look like a street photo. Please photograph the problem itself.", "यह सड़क की फ़ोटो नहीं लगती। समस्या की फ़ोटो लें।")));
  if (v.guess.key === "road_ok") notes.push(h("p", { class: "vision-warn" }, L("The road looks normal in this photo. Make sure the problem is in the frame.", "फ़ोटो में सड़क सामान्य लगती है। समस्या फ़्रेम में रखें।")));
  if (v.guess.key === "manhole_cover") notes.push(h("p", { class: "vision-warn" }, L("Looks like a closed manhole cover. Report it only if it is open, broken or sunken.", "बंद ढक्कन लगता है। खुला या टूटा हो तभी रिपोर्ट करें।")));
  if (v.guess.category && f.category && f.category !== v.guess.category && v.guess.confidence >= 0.6) {
    const suggested = v.guess.category as Category;
    notes.push(h("p", {}, L("The photo looks more like ", "फ़ोटो ज़्यादा ऐसी लगती है: ") + catLabel(suggested) + ". ",
      btn(L(`Use ${catLabel(suggested)} instead`, `${catLabel(suggested)} चुनें`), "link", () => {
        f.category = suggested;
        f.details = new Set([...f.details].filter((d) => DETAILS_FOR[suggested].includes(d)));
        render();
      })));
  }
  if (v.face >= 0.6) notes.push(h("p", { class: "vision-warn" }, L("A face may be visible. Consider retaking the photo to protect people's privacy.", "चेहरा दिख सकता है। निजता के लिए दोबारा फ़ोटो लें।")));
  if (v.potholeLarge !== null && v.potholeLarge >= 0.7 && !f.details.has("deep") && (f.category ?? "POTHOLE") === "POTHOLE") {
    notes.push(h("p", {}, L("This pothole looks large. ", "गड्ढा बड़ा लगता है। "), btn(L("Mark as deep", "गहरा चिह्नित करें"), "link", () => {
      f.details.add("deep");
      render();
    })));
  }
  return h("div", { class: "vision-card" },
    h("div", { class: "vision-head" }, h("b", {}, "Kestrel Vision"), h("span", { class: "meta" }, L("on your phone · a suggestion, you decide", "आपके फ़ोन पर · सुझाव, फ़ैसला आपका"))),
    h("div", { class: "vision-bars" }, ...top.map((t) => h("div", { class: "vision-bar" },
      h("span", {}, L(...VISION_LABEL[t.key])), h("i", {}, h("b", { style: `width:${Math.round(t.p * 100)}%` })), h("span", { class: "meta" }, likelihood(t.p))))),
    v.preselect && f.category === v.guess.category ? h("p", { class: "understood" }, L("Category filled from the photo. Change it on step 1 if wrong.", "श्रेणी फ़ोटो से भरी गई। गलत हो तो चरण 1 पर बदलें।")) : null,
    ...notes);
}

function stepExtras(): HTMLElement {
  const photoIn = h("input", { type: "file", accept: "image/*", capture: "environment", class: "visually-hidden", id: "rep-photo" }) as HTMLInputElement;
  photoIn.addEventListener("change", async () => {
    const file = photoIn.files?.[0];
    if (!file) return;
    try {
      f.photo = await compressPhoto(file);
      f.vision = "loading";
      render();
      void look(f.photo.preview);
    } catch {
      toast(L("Could not read that photo.", "फ़ोटो नहीं पढ़ी जा सकी।"), "error");
    }
  });
  return h("div", { class: "wiz-step" },
    h("div", {}, h("p", { class: "eyebrow" }, L("Step 3 of 4 · optional", "चरण 3 / 4 · वैकल्पिक")), h("h1", {}, L("Add a photo and details", "फ़ोटो और जानकारी"))),
    f.photo
      ? h("div", { class: "photo-preview" }, h("img", { src: f.photo.preview, alt: L("Your photo", "आपकी फ़ोटो") }),
          btn(L("Remove", "हटाएँ"), "link", () => {
            f.photo = undefined;
            f.vision = undefined;
            render();
          }))
      : h("label", { class: "photo-drop", for: "rep-photo" }, icon("camera", 30), L("Take or choose a photo", "फ़ोटो लें या चुनें"),
          h("span", { class: "meta" }, L("A photo makes it count more. Avoid faces and number plates.", "फ़ोटो से वज़न बढ़ता है। चेहरे और नंबर प्लेट से बचें।"))),
    photoIn,
    f.photo ? visionCard() : null,
    f.hint ? h("p", { class: "understood" }, f.hint) : null,
    h("h2", {}, L("Is any of this true?", "क्या इनमें से कुछ सही है?")),
    h("div", { class: "detail-chips" }, ...DETAILS_FOR[f.category ?? "OTHER"].map((d) => btn(L(...DETAIL_LABEL[d] as [string, string]), "chip-toggle", () => {
      if (f.details.has(d)) f.details.delete(d);
      else f.details.add(d);
      render();
    }, { "aria-pressed": String(f.details.has(d)) }))));
}

function stepReview(): HTMLElement {
  const dupes = nearby.slice(0, 4).map((i) => h("div", { class: `dupe ${f.issueId === i.issueId ? "chosen" : ""}` },
    catBadge(i.category, i.priority),
    h("div", { class: "dupe-main" }, h("b", {}, i.place || catLabel(i.category)),
      h("span", { class: "meta" }, `${i.distanceM} m · ${i.reports} ${L("reports", "रिपोर्ट")} · ${wfLabel(i.workflowState)}`)),
    btn(f.issueId === i.issueId ? L("Joined ✓", "जुड़ा ✓") : L("Same one", "यही है"), f.issueId === i.issueId ? "primary small" : "secondary small", () => {
      f.issueId = f.issueId === i.issueId ? undefined : i.issueId;
      render();
    })));
  return h("div", { class: "wiz-step" },
    h("div", {}, h("p", { class: "eyebrow" }, L("Step 4 of 4", "चरण 4 / 4")), h("h1", {}, L("Check and send", "जाँचें और भेजें"))),
    h("div", { class: "card review-card" },
      h("div", { class: "review-line" }, catBadge(f.category!), h("div", {}, h("b", {}, catLabel(f.category!)),
        h("p", { class: "meta" }, [...f.details].map((x) => L(...DETAIL_LABEL[x] as [string, string])).join(" · ") || L("No extra details", "कोई अतिरिक्त जानकारी नहीं")))),
      h("p", { class: "meta" }, icon("pin", 14), " ", f.place || `${f.lat?.toFixed(5)}, ${f.lon?.toFixed(5)}`),
      f.text ? h("p", {}, `“${f.text}”`) : null,
      f.photo ? h("img", { src: f.photo.preview, alt: "", style: "width:120px;border-radius:12px" }) : null),
    h("h2", {}, nearby.length ? L("Is it one of these?", "क्या यह इनमें से एक है?") : L("No similar issue nearby", "पास में ऐसी कोई समस्या नहीं")),
    nearby.length ? h("p", { class: "meta" }, L("Joining adds your voice and raises its priority instead of creating a duplicate.",
      "जुड़ने से आपकी आवाज़ जुड़ती है और प्राथमिकता बढ़ती है।"))
      : h("p", { class: "meta" }, L("Yours will start a new issue. A second person confirming it makes it verified.", "आपकी रिपोर्ट नई समस्या बनेगी।")),
    h("div", { class: "dupes" }, ...dupes),
    h("p", { class: "fineprint" }, L("Reports are claims, not measurements. Each person counts once per issue. Demo data is synthetic. ",
      "रिपोर्ट दावा है, माप नहीं। हर व्यक्ति एक बार गिना जाता है। "),
      btn(L("Demo: act as another citizen", "डेमो: दूसरा नागरिक बनें"), "link", () => toast(L("Now reporting as ", "अब इस नाम से: ") + newCitizenId()))));
}

function done(): HTMLElement {
  const { r, queued } = result!;
  return h("div", { class: "wiz-step rep-done" },
    h("div", { class: "done-check" }, icon("check", 44)),
    ...(queued || !r
      ? [h("h1", {}, L("Saved on your phone", "आपके फ़ोन में सुरक्षित")),
         h("p", { class: "muted" }, L("No connection right now. It sends itself when you're back online, with the time you saw it.",
           "अभी नेटवर्क नहीं है। नेटवर्क आते ही रिपोर्ट अपने-आप जाएगी।"))]
      : [h("h1", {}, r.joined ? L("Added to an existing issue", "मौजूदा समस्या में जोड़ा गया") : L("New issue created", "नई समस्या बनी")),
         h("p", { class: "muted" }, r.joined
           ? L(`You're one of ${r.sources} people who reported this. It now has ${r.reports} reports.`, `इसे ${r.sources} लोगों ने बताया है। अब ${r.reports} रिपोर्ट हैं।`)
           : L("You're the first. When a second person confirms it, it becomes verified.", "आप पहले हैं। दूसरे की पुष्टि पर सत्यापित होगी।")),
         h("p", {}, priorityChip(r.priority, r.score), " ", h("span", { class: `wf wf-${r.workflowState.toLowerCase()}` }, wfLabel(r.workflowState))),
         h("a", { class: "primary big", href: `#/i/${r.issueId}` }, L("Track this issue", "इस समस्या को ट्रैक करें") + ` · ${r.issueId}`)]),
    btn(L("Report another", "एक और रिपोर्ट"), "secondary big", restart));
}

function render(): void {
  if (result) {
    root.replaceChildren(h("div", { class: "wiz" }, done()));
    return;
  }
  const body = [stepWhat, stepWhere, stepExtras, stepReview][step]();
  const next = btn(step === 3 ? h("span", {}, L("Send report", "रिपोर्ट भेजें"), icon("arrow", 18)) : h("span", {}, L("Continue", "आगे"), icon("arrow", 18)),
    `primary big wiz-next ${step === 3 ? "amber" : ""}`, () => {
      if (!ready()) return;
      if (step === 3) return void submit();
      step += 1;
      if (step === 3) void loadNearby();
      render();
      focusStep();
    });
  const back = step > 0 ? btn(L("Back", "पीछे"), "secondary big", () => {
    step -= 1;
    render();
    focusStep();
  }, { style: "flex:0 0 30%" }) : null;
  root.replaceChildren(h("div", { class: "wiz" },
    h("div", { class: "wizard-top" }, h("a", { href: "#/", class: "back" }, "← ", L("Overview", "अवलोकन")), h("span", { class: "meta" }, L("Report an issue", "समस्या रिपोर्ट करें"))),
    h("ol", { class: "report-steps", "aria-label": L("Report progress", "रिपोर्ट प्रगति") },
      ...[["Problem", "समस्या"], ["Location", "जगह"], ["Details", "जानकारी"], ["Review", "जाँच"]].map(([en, hi], i) =>
        h("li", { class: i <= step ? "on" : "", ...(i === step ? { "aria-current": "step" } : {}) },
          h("span", {}, i < step ? "✓" : String(i + 1)), L(en, hi)))),
    body,
    h("div", { class: "wiz-nav" }, ...kids(back, next))));
  syncNav();
}

export async function showReport(el: HTMLElement, preset?: Category): Promise<void> {
  root = el;
  if (preset && !result) f.category = preset;
  render();
}
