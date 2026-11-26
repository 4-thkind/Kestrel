/** Shared civic UI: DOM helper, category icons, labels (EN/HI), formatting. */
import { getLang } from "../flood/i18n.ts";
import type { Category, EvidenceState, Priority, WorkflowState } from "./api.ts";

type Child = Node | string | null | undefined | false;

export function h(tag: string, props: Record<string, string> = {}, ...children: Child[]): HTMLElement {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") el.className = v;
    else el.setAttribute(k, v);
  }
  for (const c of children) if (c !== null && c !== undefined && c !== false) el.append(c);
  return el;
}

export function btn(label: string | Node, cls: string, onClick: () => void, attrs: Record<string, string> = {}): HTMLButtonElement {
  const b = h("button", { type: "button", class: cls, ...attrs }, label) as HTMLButtonElement;
  b.addEventListener("click", onClick);
  return b;
}

/** Bilingual text: pick by current language. */
export const L = (en: string, hi: string): string => (getLang() === "hi" ? hi : en);

const ICON_PATHS: Record<Category | "route" | "camera" | "mic" | "pin" | "check" | "x" | "share" | "map" | "chart" | "plus" | "shield" | "locate" | "arrow", string> = {
  map: '<path d="M9 4 3 6.5v13.5L9 17.5l6 2.5 6-2.5V4l-6 2.5z"/><path d="M9 4v13.5M15 6.5V20"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  shield: '<path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.4 7.5 9.5 4.3-1.1 7.5-4.9 7.5-9.5V6z"/><path d="m9 12 2.2 2.2L15.5 10"/>',
  locate: '<circle cx="12" cy="12" r="7.5"/><circle cx="12" cy="12" r="2.5"/><path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  POTHOLE: '<path d="M3 20 8 4M21 20 16 4"/><ellipse cx="12" cy="14" rx="5" ry="2.4"/><path d="M12 6v2"/>',
  WATERLOGGING: '<path d="M2 15c2 0 2.5-1.6 5-1.6S9.5 15 12 15s2.5-1.6 5-1.6 3 1.6 5 1.6M2 19.5c2 0 2.5-1.6 5-1.6s2.5 1.6 5 1.6 2.5-1.6 5-1.6 3 1.6 5 1.6"/><path d="M12 3v7M9 7.5l3 3 3-3"/>',
  OPEN_MANHOLE: '<circle cx="12" cy="13.5" r="7.5"/><circle cx="12" cy="13.5" r="3.2"/><path d="M12 2.5v2.5"/>',
  BLOCKED_ROAD: '<rect x="2.5" y="8" width="19" height="5.5" rx="1"/><path d="M7.5 8 5 13.5M13 8l-2.5 5.5M18.5 8 16 13.5M5.5 13.5V21M18.5 13.5V21"/>',
  GARBAGE_DUMP: '<path d="M4 7h16M9 7V4h6v3M6 7l1.2 13.5h9.6L18 7M10 11v6M14 11v6"/>',
  STREETLIGHT_OUT: '<path d="M7 21h6M10 21V6a3 3 0 0 1 3-3h4"/><path d="M15.5 3 18 8h-5z"/><path d="M3 3l18 18"/>',
  OTHER: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.5v.1"/>',
  route: '<circle cx="6" cy="19" r="2"/><circle cx="18" cy="5" r="2"/><path d="M8 19h8a3.5 3.5 0 0 0 0-7H8a3.5 3.5 0 0 1 0-7h8"/>',
  camera: '<path d="M3 8h4l2-3h6l2 3h4v12H3z"/><circle cx="12" cy="13.5" r="3.5"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  pin: '<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
  check: '<path d="M4 12.5 9.5 18 20 6.5"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  share: '<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="m8.2 10.8 7.6-3.6M8.2 13.2l7.6 3.6"/>',
};

export function icon(name: keyof typeof ICON_PATHS, size = 22): SVGElement {
  const wrap = document.createElement("span");
  wrap.innerHTML = `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[name]}</svg>`;
  return wrap.firstElementChild as SVGElement;
}

export const CATEGORIES: Category[] = ["POTHOLE", "GARBAGE_DUMP", "STREETLIGHT_OUT", "OPEN_MANHOLE", "WATERLOGGING", "BLOCKED_ROAD", "OTHER"];

export const CAT_LABEL: Record<Category, [string, string]> = {
  POTHOLE: ["Pothole", "गड्ढा"],
  WATERLOGGING: ["Waterlogging", "जलभराव"],
  OPEN_MANHOLE: ["Open manhole", "खुला मैनहोल"],
  BLOCKED_ROAD: ["Blocked road", "रास्ता बंद"],
  GARBAGE_DUMP: ["Garbage dump", "कूड़े का ढेर"],
  STREETLIGHT_OUT: ["Streetlight out", "स्ट्रीटलाइट बंद"],
  OTHER: ["Other", "अन्य"],
};
export const catLabel = (c: Category): string => L(...CAT_LABEL[c]);

export const EVIDENCE_LABEL: Record<EvidenceState, [string, string]> = {
  UNKNOWN: ["No reports", "कोई रिपोर्ट नहीं"],
  REPORTED: ["Reported by 1 person", "1 व्यक्ति ने बताया"],
  CORROBORATED: ["Confirmed by several people", "कई लोगों ने पुष्टि की"],
  CONFLICTED: ["People disagree, needs a check", "लोगों में असहमति, जाँच चाहिए"],
  STALE: ["Not re-checked recently, still open", "हाल में जाँच नहीं, अभी खुला"],
  CLEAR_REPORTED: ["Citizens report it fixed", "नागरिकों के अनुसार ठीक"],
};

export const WORKFLOW_LABEL: Record<WorkflowState, [string, string]> = {
  OPEN: ["Open", "खुला"],
  VERIFIED: ["Verified", "सत्यापित"],
  ASSIGNED: ["Assigned", "सौंपा गया"],
  IN_PROGRESS: ["Work in progress", "काम जारी"],
  RESOLVED: ["Resolved, awaiting citizens", "हल, नागरिक पुष्टि बाकी"],
  REOPENED: ["Reopened", "फिर खोला"],
  CLOSED: ["Closed, citizen-confirmed", "बंद, नागरिक पुष्टि"],
  CLOSED_UNCONFIRMED: ["Closed, not confirmed", "बंद, पुष्टि नहीं"],
  REJECTED: ["Rejected", "अस्वीकृत"],
  MERGED: ["Merged as duplicate", "डुप्लिकेट, मिला दिया"],
};
export const wfLabel = (w: WorkflowState): string => L(...WORKFLOW_LABEL[w]);

/** Lifecycle shown as a stepper; side states map onto the nearest step. */
export const STEPS: WorkflowState[] = ["OPEN", "VERIFIED", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED"];
export function stepIndex(w: WorkflowState): number {
  const map: Partial<Record<WorkflowState, number>> = { REOPENED: 2, CLOSED_UNCONFIRMED: 5, REJECTED: -1, MERGED: -1 };
  return map[w] ?? STEPS.indexOf(w);
}

export const PRIORITY_LABEL: Record<Priority, [string, string]> = {
  P1: ["P1 urgent", "P1 अति आवश्यक"],
  P2: ["P2 high", "P2 ज़रूरी"],
  P3: ["P3 routine", "P3 सामान्य"],
};

export const DETAIL_LABEL: Record<string, [string, string]> = {
  deep: ["Deep", "गहरा"],
  wide: ["Wide", "चौड़ा"],
  near_school: ["Near a school", "स्कूल के पास"],
  near_hospital: ["Near a hospital", "अस्पताल के पास"],
  major_road: ["Main road", "मुख्य सड़क"],
  night_hazard: ["Dangerous at night", "रात में खतरनाक"],
  vehicles_stuck: ["Vehicles stuck", "गाड़ियाँ फंसी"],
};

export function priorityChip(p: Priority, score?: number): HTMLElement {
  return h("span", { class: `prio prio-${p.toLowerCase()}`, title: L("Severity score", "गंभीरता स्कोर") },
    L(...PRIORITY_LABEL[p]) + (score !== undefined ? ` · ${score}` : ""));
}

export function catBadge(c: Category, priority?: Priority): HTMLElement {
  return h("span", { class: `cat-badge cat-${c.toLowerCase()} ${priority ? "prio-bg-" + priority.toLowerCase() : ""}` }, icon(c, 20));
}

export function ago(isoTime: string): string {
  const s = Math.max(0, (Date.now() - Date.parse(isoTime)) / 1000);
  const [n, en, hi] =
    s < 90 ? [0, "just now", "अभी"]
    : s < 5400 ? [Math.round(s / 60), "min ago", "मिनट पहले"]
    : s < 129600 ? [Math.round(s / 3600), "h ago", "घंटे पहले"]
    : [Math.round(s / 86400), "d ago", "दिन पहले"];
  return n ? `${n} ${L(en, hi)}` : L(en, hi);
}

export function fmtDate(isoTime: string): string {
  return new Date(isoTime).toLocaleString(getLang() === "hi" ? "hi-IN" : "en-IN",
    { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

let toastTimer: number | undefined;
export function toast(text: string, kind: "ok" | "warn" | "error" = "ok"): void {
  let el = document.getElementById("toast");
  if (!el) {
    el = h("div", { id: "toast", role: "status", "aria-live": "polite" });
    document.body.append(el);
  }
  el.className = `toast toast-${kind} show`;
  el.textContent = text;
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => el?.classList.remove("show"), 3800);
}

/** Stable synthetic citizen id per browser, so two phones are two distinct sources. */
/** Covexcode "ward pulse": fills in when ready, disappears if the model is off or slow. */
export function wardPulse(wardId: string, pulse: (w: string) => Promise<{ pulse: { en: string; hi: string | null; modelId: string; issues: number } | null }>): HTMLElement {
  const box = h("section", { class: "ai-brief" }, h("p", { class: "meta" }, L("Ward pulse loading…", "वार्ड का हाल लोड हो रहा है…")));
  pulse(wardId).then(({ pulse: p }) => {
    if (!p) return box.remove();
    box.replaceChildren(
      h("p", { class: "ai-brief-head" }, h("b", {}, L("Ward pulse", "वार्ड का हाल")), h("span", { class: "meta" }, ` · AI summary · Covexcode ${p.modelId}`)),
      h("p", {}, L(p.en, p.hi ?? p.en)),
      h("p", { class: "fineprint" }, L("Written from this ward's open issues and scorecard only.", "केवल इस वार्ड की खुली समस्याओं और स्कोरकार्ड से लिखा गया।")));
  }).catch(() => box.remove());
  return box;
}

export function citizenId(): string {
  try {
    let id = localStorage.getItem("kestrel.citizen");
    if (!id) {
      id = "demo-" + crypto.randomUUID().slice(0, 8);
      localStorage.setItem("kestrel.citizen", id);
    }
    return id;
  } catch {
    return "demo-anon";
  }
}

export function newCitizenId(): string {
  const id = "demo-" + crypto.randomUUID().slice(0, 8);
  try {
    localStorage.setItem("kestrel.citizen", id);
  } catch {
    /* session only */
  }
  return id;
}

/** Downscale a photo to at most 960 px and JPEG-encode it under the server's 300 KB limit. */
export async function compressPhoto(file: File): Promise<{ contentType: "image/jpeg"; data: string; preview: string }> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 960 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  for (const quality of [0.72, 0.6, 0.45, 0.32]) {
    const url = canvas.toDataURL("image/jpeg", quality);
    const data = url.slice(url.indexOf(",") + 1);
    if (data.length * 0.75 < 290_000) return { contentType: "image/jpeg", data, preview: url };
  }
  throw new Error("PHOTO_TOO_LARGE");
}

/** Model scores in words: a softmax "100%" overstates what was measured (~94% at the top band). */
export function likelihood(p: number): string {
  return p >= 0.8 ? L("very likely", "बहुत संभव") : p >= 0.5 ? L("likely", "संभव") : p >= 0.2 ? L("possible", "शायद") : L("unlikely", "कम संभव");
}

/** replaceChildren() rejects null; drop the empty slots of conditional children. */
export const kids = (...c: Child[]): (Node | string)[] => c.filter((x): x is Node | string => x !== null && x !== undefined && x !== false);
