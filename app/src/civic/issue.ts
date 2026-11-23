/** Public issue page (#/i/<id>): what, where, how sure, how urgent, who owns it, and every step so far. */
import { ApiFailure } from "../flood/api.ts";
import { createMap, type Layer, type MapView } from "../map/mapview.ts";
import { civicApi, type IssueDetail } from "./api.ts";
import { embed, loadImage, sameSpot, stillThere } from "./vision.ts";
import {
  DETAIL_LABEL, EVIDENCE_LABEL, L, STEPS, likelihood, ago, btn, catLabel, citizenId, fmtDate, h, icon, priorityChip, stepIndex, toast, wfLabel,
} from "./ui.ts";

let map: MapView | undefined;
let pin: Layer | undefined;
let clientMode = "LOCAL_DEMO";

export function setIssueClientMode(mode: string): void {
  clientMode = mode;
}

function stepper(d: IssueDetail): HTMLElement {
  const at = stepIndex(d.workflowState);
  if (at < 0) {
    return h("div", { class: "stepper-side" }, h("b", {}, wfLabel(d.workflowState)),
      d.workflow.rejectReason ? h("p", {}, d.workflow.rejectReason) : null,
      d.workflow.mergedInto ? h("p", {}, L("Duplicate of ", "इसका डुप्लिकेट: "), h("a", { href: `#/i/${d.workflow.mergedInto}` }, d.workflow.mergedInto)) : null);
  }
  return h("ol", { class: "stepper", "aria-label": L("Progress", "प्रगति") }, ...STEPS.map((s, i) =>
    h("li", { class: i < at ? "done" : i === at ? "now" : "" }, h("span", { class: "dot" }), h("span", { class: "lbl" },
      i === at ? wfLabel(d.workflowState) : wfLabel(s)))));
}

function severityBars(d: IssueDetail): HTMLElement {
  return h("div", { class: "sev" },
    h("div", { class: "sev-head" }, priorityChip(d.priority), h("b", { class: "sev-score" }, `${d.score}`, h("small", {}, "/100"))),
    h("ul", { class: "sev-parts" }, ...d.severity.parts.map((p) => h("li", {},
      h("span", {}, p.label), h("span", { class: "bar" }, h("i", { style: `width:${Math.min(100, p.points * 2.5)}%` })), h("b", {}, `+${p.points}`)))),
    h("p", { class: "fineprint" }, L("Score = category base + people confirming + photo + exposure + days overdue. Capped at 100. P1 ≥ 70, P2 ≥ 40.",
      "स्कोर = श्रेणी + पुष्टि करने वाले लोग + फ़ोटो + जगह + देरी। अधिकतम 100।")));
}

function timeline(d: IssueDetail): HTMLElement {
  const who: Record<string, string> = { citizen: L("Citizen", "नागरिक"), officer: L("Ward officer", "वार्ड अधिकारी"),
    community: L("Community rule", "सामुदायिक नियम"), system: L("System", "सिस्टम") };
  return h("ol", { class: "timeline" }, ...[...d.timeline].reverse().map((e) =>
    h("li", { class: `tl tl-${e.actor}` },
      h("span", { class: "tl-dot" }),
      h("div", {},
        h("div", { class: "tl-head" }, h("b", {}, e.label), h("span", { class: "meta" }, ` · ${e.source ?? who[e.actor]} · ${fmtDate(e.at)}`)),
        e.note ? h("p", { class: "tl-note" }, e.note) : null,
        e.photoUrl ? h("img", { class: "tl-photo", src: e.photoUrl, alt: L("Photo", "फ़ोटो"), loading: "lazy" }) : null))));
}

async function vote(d: IssueDetail, kind: "STILL_THERE" | "FIXED", el: HTMLElement): Promise<void> {
  try {
    const r = await civicApi.vote(d.issueId, kind, clientMode, citizenId());
    toast(r.duplicate ? L("Already counted.", "पहले ही गिना गया।")
      : kind === "FIXED" ? L("Thanks. Two people saying 'fixed' closes it.", "धन्यवाद। दो लोगों के 'ठीक' कहने पर बंद होगा।")
      : L("Thanks. Your confirmation raises its priority.", "धन्यवाद। आपकी पुष्टि से प्राथमिकता बढ़ी।"));
    await showIssue(el, d.issueId);
  } catch (err) {
    toast(err instanceof ApiFailure ? err.message : String(err), "error");
  }
}

async function share(d: IssueDetail): Promise<void> {
  const url = `${location.origin}/#/i/${d.issueId}`;
  const text = `${catLabel(d.category)}${d.place ? " at " + d.place : ""}: ${d.reports} reports, ${d.priority}, ${wfLabel(d.workflowState)}. Track it on Kestrel:`;
  try {
    if (navigator.share) await navigator.share({ title: "Kestrel " + d.issueId, text, url });
    else location.href = `https://wa.me/?text=${encodeURIComponent(text + " " + url)}`;
  } catch {
    /* share sheet dismissed */
  }
}

export async function showIssue(el: HTMLElement, id: string): Promise<void> {
  let d: IssueDetail;
  try {
    d = await civicApi.issue(id);
  } catch (err) {
    el.replaceChildren(h("div", { class: "page" }, h("h1", {}, L("Issue not found", "समस्या नहीं मिली")),
      h("p", {}, err instanceof ApiFailure ? err.message : String(err)), h("a", { href: "#/", class: "secondary" }, L("Back to map", "नक्शे पर लौटें"))));
    return;
  }
  const closed = ["CLOSED", "CLOSED_UNCONFIRMED", "REJECTED", "MERGED"].includes(d.workflowState);
  const photos = d.observations.filter((o) => o.photoUrl);
  const mapBox = h("div", { class: "issue-map", id: "issue-map" });
  el.replaceChildren(h("div", { class: "page issue" },
    h("a", { href: "#/", class: "back" }, "← ", L("All issues", "सभी समस्याएँ")),
    h("header", { class: `issue-hero ${closed ? "" : d.priority.toLowerCase()}` },
      h("div", { class: "hero-top" }, h("span", { class: "hero-icon" }, icon(d.category, 30)),
        h("div", {},
          h("p", { class: "eyebrow" }, `${d.issueId} · ${d.ward ? L(d.ward.name, d.ward.nameHi) + " · " + d.ward.agency : L("Outside sample wards", "नमूना वार्ड के बाहर")}`),
          h("h1", {}, catLabel(d.category), d.place ? h("span", { class: "place" }, d.place) : null))),
      h("div", { class: "hero-status" },
        h("span", { class: "pill" }, wfLabel(d.workflowState)),
        h("span", { class: "pill" }, `${d.priority} · ${d.score}/100`),
        d.overdueDays > 0 ? h("span", { class: "pill" }, `${d.overdueDays} ${L("days overdue", "दिन देर")}`) : null),
      h("div", { class: "hero-facts" },
        h("div", {}, h("b", {}, String(d.reports)), h("span", {}, L("reports", "रिपोर्ट"))),
        h("div", {}, h("b", {}, String(d.sources)), h("span", {}, L("people", "लोग"))),
        h("div", {}, h("b", {}, String(d.photos)), h("span", {}, L("photos", "फ़ोटो"))),
        h("div", {}, h("b", {}, ago(d.openedAt).replace(/ ago| पहले/, "")), h("span", {}, L("open for", "से खुला"))))),
    h("div", { class: "issue-grid" },
      h("div", { class: "col" },
        h("section", { class: "card" }, stepper(d),
          d.workflow.assignee ? h("p", { class: "meta" }, L("Assigned to ", "सौंपा: ") + d.workflow.assignee) : null,
          h("p", { class: "fineprint" }, L("Likely owner: ", "संभावित ज़िम्मेदार: ") + d.categoryInfo.owner)),
        !closed ? h("section", { class: "card vote" },
          h("h2", {}, L("Are you near it now?", "क्या आप अभी पास हैं?")),
          h("div", { class: "vote-row" },
            btn(h("span", {}, icon("x", 18), L("Still there", "अभी भी है")), "vote-still", () => void vote(d, "STILL_THERE", el)),
            btn(h("span", {}, icon("check", 18), L("It's fixed", "ठीक हो गया")), "vote-fixed", () => void vote(d, "FIXED", el))),
          h("p", { class: "fineprint" }, d.workflowState === "RESOLVED"
            ? L("The ward marked this resolved. It closes only when two people confirm the fix; two 'still there' votes reopen it.",
              "वार्ड ने हल बताया। दो लोगों की पुष्टि पर ही बंद होगा; दो 'अभी भी है' पर फिर खुलेगा।")
            : L("Votes count once per person. Two 'fixed' votes clear it.", "हर व्यक्ति एक बार गिना जाता है।"))) : null,
        h("section", { class: "card" }, h("h2", {}, L("How urgent", "कितना ज़रूरी")), severityBars(d)),
        h("section", { class: "card" }, h("h2", {}, L("Evidence", "सबूत")),
          h("p", {}, h("b", {}, L(...EVIDENCE_LABEL[d.evidenceState]))),
          h("p", { class: "meta" }, `${d.reports} ${L("reports", "रिपोर्ट")} · ${d.sources} ${L("different people", "अलग लोग")} · ${d.photos} ${L("photos", "फ़ोटो")}`),
          d.details.length ? h("div", { class: "tags" }, ...d.details.map((x) => h("span", { class: "tag" }, L(...(DETAIL_LABEL[x] ?? [x, x]) as [string, string])))) : null,
          d.blocksRoute ? h("p", { class: "routes-flag" }, icon("route", 16), L(" Kestrel routes avoid this spot while it is open.", " खुला रहने तक Kestrel रास्ते इससे बचते हैं।")) : null,
          h("p", { class: "fineprint" }, L("Reports are claims from citizens, not measurements.", "रिपोर्ट नागरिकों के दावे हैं, माप नहीं।"))),
        h("section", { class: "card", id: "vision-checks", hidden: "" }, h("h2", {}, "Kestrel Vision")),
        photos.length ? h("section", { class: "card" }, h("h2", {}, L("Photos", "फ़ोटो")),
          h("div", { class: "photos" }, ...photos.map((o) => h("img", { src: o.photoUrl!, alt: `${o.source} · ${fmtDate(o.observedAt)}`, loading: "lazy" })))) : null),
      h("div", { class: "col" },
        mapBox,
        h("div", { class: "actions" }, btn(h("span", {}, icon("share", 18), L("Share", "शेयर")), "secondary", () => void share(d)),
          h("a", { class: "secondary", href: `#/wards/${d.wardId}` }, L("Ward scorecard", "वार्ड स्कोरकार्ड"))),
        h("section", { class: "card" }, h("h2", {}, L("Timeline", "समयरेखा")), timeline(d))),
    )));
  map = await createMap(mapBox, { center: [d.lon, d.lat], zoom: 16, interactive: true });
  pin = map.layer();
  pin.pin([d.lon, d.lat], h("span", { class: `map-pin prio-bg-${d.priority.toLowerCase()}` }, icon(d.category, 16)));
  void visionChecks(d, el.querySelector<HTMLElement>("#vision-checks")!);
}

/** Checks a viewer's own browser runs on the public photos, so an officer cannot fake them. */
async function visionChecks(d: IssueDetail, box: HTMLElement): Promise<void> {
  const citizen = d.observations.filter((o) => o.photoUrl).map((o) => o.photoUrl!).slice(0, 6);
  const after = [...d.timeline].reverse().find((e) => e.action === "RESOLVE" && e.photoUrl)?.photoUrl;
  if (!after && citizen.length < 2) return;
  const rows: HTMLElement[] = [];
  try {
    if (after) {
      const p = await stillThere(await loadImage(after));
      rows.push(h("p", { class: `vision-check ${p >= 0.5 ? "bad" : "good"}` }, icon(p >= 0.5 ? "x" : "check", 16),
        p >= 0.5 ? L(`The after-photo still looks like a problem (${likelihood(p)}). Citizen votes decide.`, `मरम्मत के बाद की फ़ोटो में अब भी समस्या दिखती है (${likelihood(p)})।`)
          : L(`The after-photo looks fixed (${likelihood(1 - p)}). Citizen votes still decide.`, `मरम्मत के बाद की फ़ोटो ठीक लगती है (${likelihood(1 - p)})।`)));
    }
    if (citizen.length >= 2) {
      const embs = [];
      for (const url of citizen) embs.push(await embed(await loadImage(url)));
      let agree = 0;
      for (const e of embs.slice(1)) if (await sameSpot(embs[0], e)) agree += 1;
      rows.push(h("p", { class: "vision-check" }, icon("camera", 16),
        L(`${agree + 1} of ${embs.length} photos look like the same spot.`, `${embs.length} में से ${agree + 1} फ़ोटो एक ही जगह की लगती हैं।`)));
    }
  } catch (err) {
    console.warn("[vision]", err);
    return;
  }
  box.append(...rows, h("p", { class: "fineprint" }, L("Computed on this device by a small open model. A hint, never a decision.", "इस डिवाइस पर गणना। संकेत मात्र, फ़ैसला नहीं।")));
  box.hidden = false;
}
