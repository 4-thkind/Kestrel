/** Ward officer console: one deduplicated, priority-sorted queue per ward, and the actions that move an issue.
 * Every action lands on the public timeline. Demo mode signs in as the chosen ward's officer (synthetic). */
import { ApiFailure } from "../flood/api.ts";
import { civicApi, type IssueDetail, type IssueSummary, type Ward } from "./api.ts";
import { loadImage, stillThere } from "./vision.ts";
import { L, ago, btn, likelihood, catBadge, catLabel, compressPhoto, fmtDate, h, kids, priorityChip, toast, wardPulse, wfLabel } from "./ui.ts";

const TEAMS = ["Road maintenance division", "Sanitation team", "Electrical maintenance team", "Sewer maintenance team",
  "Drainage team", "Horticulture and malba removal team", "Ward civil team"];
const ACTIONS_FOR: Record<string, string[]> = {
  OPEN: ["ASSIGN", "MERGE", "REJECT"], VERIFIED: ["ASSIGN", "MERGE", "REJECT"], REOPENED: ["ASSIGN", "MERGE", "REJECT"],
  ASSIGNED: ["START", "RESOLVE", "ASSIGN", "REJECT"], IN_PROGRESS: ["RESOLVE"],
};
const ACTION_LABEL: Record<string, [string, string]> = {
  ASSIGN: ["Assign", "सौंपें"], START: ["Start work", "काम शुरू"], RESOLVE: ["Mark resolved", "हल हुआ"],
  REJECT: ["Reject", "अस्वीकार"], MERGE: ["Merge duplicate", "डुप्लिकेट मिलाएँ"],
};

let ward = "";
let selected: string | undefined;

function actionForm(d: IssueDetail, queue: IssueSummary[], refresh: () => Promise<void>): HTMLElement {
  const actions = ACTIONS_FOR[d.workflowState] ?? [];
  if (!actions.length) return h("p", { class: "muted" }, L("Waiting for citizens to confirm. No action needed.", "नागरिक पुष्टि का इंतज़ार।"));
  let action = actions[0];
  let photo: { contentType: "image/jpeg"; data: string } | undefined;
  const team = h("select", { id: "off-team" }, ...TEAMS.map((t) => h("option", {}, t))) as HTMLSelectElement;
  const note = h("textarea", { rows: "2", maxlength: "500", placeholder: L("Public note (shown on the issue page)", "सार्वजनिक नोट") }) as HTMLTextAreaElement;
  const target = h("select", {}, ...queue.filter((q) => q.issueId !== d.issueId && q.category === d.category)
    .map((q) => h("option", { value: q.issueId }, `${q.issueId} · ${q.place ?? ""}`))) as HTMLSelectElement;
  const photoIn = h("input", { type: "file", accept: "image/*", capture: "environment" }) as HTMLInputElement;
  const check = h("p", { class: "vision-check", hidden: "" });
  photoIn.addEventListener("change", async () => {
    const f = photoIn.files?.[0];
    if (f) photo = await compressPhoto(f).catch(() => undefined);
    if (!photo) return;
    // the same check every citizen's browser runs on the public issue page
    try {
      const p = await stillThere(await loadImage("data:image/jpeg;base64," + photo.data));
      check.className = `vision-check ${p >= 0.5 ? "bad" : "good"}`;
      check.textContent = p >= 0.5
        ? L(`Kestrel Vision: this still looks like a problem (${likelihood(p)}). Citizens will see this check.`, `यह अब भी समस्या जैसा लगता है (${likelihood(p)})।`)
        : L(`Kestrel Vision: looks fixed (${likelihood(1 - p)}).`, `ठीक लगता है (${likelihood(1 - p)})।`);
      check.hidden = false;
    } catch {
      check.hidden = true;
    }
  });
  const fields = h("div", { class: "off-fields" });
  const renderFields = () => fields.replaceChildren(...kids(
    action === "ASSIGN" ? h("label", {}, L("Team or agency", "टीम या एजेंसी"), team) : null,
    action === "MERGE" ? h("label", {}, L("Duplicate of", "इसका डुप्लिकेट"), target) : null,
    action === "RESOLVE" ? h("label", {}, L("After-photo of the fixed site", "मरम्मत के बाद की फ़ोटो"), photoIn) : null,
    action === "RESOLVE" ? check : null,
    h("label", {}, L("Note", "नोट") + (action === "RESOLVE" || action === "REJECT" ? " *" : ""), note)));
  const tabs = h("div", { class: "seg" }, ...actions.map((a) => {
    const b = btn(L(...ACTION_LABEL[a]), "", () => {
      action = a;
      for (const x of tabs.children) x.setAttribute("aria-pressed", String(x === b));
      renderFields();
    }, { "aria-pressed": String(a === action) });
    return b;
  }));
  renderFields();
  const go = btn(L("Apply", "लागू करें"), "primary", async () => {
    go.disabled = true;
    try {
      await civicApi.transition(d.issueId, ward, {
        action, inspectedRevision: d.revision,
        ...(note.value.trim() ? { note: note.value.trim() } : {}),
        ...(action === "ASSIGN" ? { assignee: team.value } : {}),
        ...(action === "MERGE" ? { targetIssueId: target.value } : {}),
        // only the two fields the API accepts: compressPhoto() also returns a `preview` data URL
        ...(action === "RESOLVE" && photo ? { afterPhoto: { contentType: photo.contentType, data: photo.data } } : {}),
      });
      toast(L("Saved. The public timeline shows it now.", "सहेजा गया। सार्वजनिक समयरेखा पर दिख रहा है।"));
      await refresh();
    } catch (err) {
      toast(err instanceof ApiFailure ? `${err.code}: ${err.message}` : String(err), "error");
      go.disabled = false;
    }
  });
  return h("div", { class: "off-form" }, tabs, fields, go);
}

/** Covexcode condenses every citizen description into a two-language brief; it fills in when ready. */
function aiBrief(id: string): HTMLElement {
  const box = h("div", { class: "ai-brief" }, h("p", { class: "meta" }, L("AI brief loading…", "AI सारांश लोड हो रहा है…")));
  civicApi.brief(id, ward).then(({ brief }) => {
    if (!brief) return box.remove();
    box.replaceChildren(
      h("p", { class: "ai-brief-head" }, h("b", {}, L("AI brief", "AI सारांश")), h("span", { class: "meta" }, ` · Covexcode ${brief.modelId} · ${brief.notes} ${L("citizen notes", "नागरिक टिप्पणियाँ")}`)),
      h("p", {}, L(brief.en, brief.hi ?? brief.en)),
      h("p", { class: "fineprint" }, L("Summarised from what citizens wrote. Check the reports before acting.", "नागरिकों के लिखे से सारांश। कार्रवाई से पहले रिपोर्ट देखें।")));
  }).catch(() => box.remove());
  return box;
}

async function detail(box: HTMLElement, id: string, queue: IssueSummary[], refresh: () => Promise<void>): Promise<void> {
  const d = await civicApi.issue(id);
  box.replaceChildren(...kids(
    h("div", { class: "off-detail-head" }, catBadge(d.category, d.priority),
      h("div", {}, h("h2", {}, catLabel(d.category), d.place ? " · " + d.place : ""),
        h("p", { class: "meta" }, `${d.issueId} · ${wfLabel(d.workflowState)} · ${L("due", "समय सीमा")} ${fmtDate(d.dueAt)}`))),
    h("div", { class: "off-facts" }, priorityChip(d.priority, d.score),
      h("span", { class: "meta" }, `${d.reports} ${L("reports", "रिपोर्ट")} · ${d.sources} ${L("people", "लोग")} · ${d.photos} ${L("photos", "फ़ोटो")}`)),
    h("ul", { class: "sev-mini" }, ...d.severity.parts.map((p) => h("li", {}, `${p.label} +${p.points}`))),
    d.observations.some((o) => o.photoUrl) ? h("div", { class: "photos" }, ...d.observations.filter((o) => o.photoUrl)
      .map((o) => h("img", { src: o.photoUrl!, alt: o.source }))) : null,
    h("ul", { class: "quotes" }, ...d.observations.filter((o) => o.description).slice(-3).map((o) => h("li", {}, `“${o.description}” `, h("span", { class: "meta" }, o.source)))),
    aiBrief(d.issueId),
    actionForm(d, queue, refresh),
    h("a", { class: "link", href: `#/i/${d.issueId}` }, L("Open public page", "सार्वजनिक पेज खोलें"))));
}

export async function showOfficer(el: HTMLElement, wardId?: string): Promise<void> {
  let wards: Ward[] = [];
  try {
    wards = (await civicApi.wards()).wards;
  } catch {
    toast(L("Could not load wards.", "वार्ड लोड नहीं हुए।"), "error");
  }
  ward = wardId ?? ward ?? "";
  if (!ward || !wards.some((w) => w.id === ward)) {
    el.replaceChildren(h("div", { class: "page" },
      h("header", { class: "page-head" }, h("h1", {}, L("Ward officer console", "वार्ड अधिकारी कंसोल")),
        h("p", { class: "muted" }, L("Demo sign-in: pick a ward to act as its officer. Real pilots use a ward-scoped login.",
          "डेमो: वार्ड चुनें। असली पायलट में वार्ड-लॉगिन होगा।"))),
      h("div", { class: "ward-grid" }, ...wards.map((w) => h("a", { class: "card ward-pick", href: `#/officer/${w.id}` },
        h("h2", {}, L(w.name, w.nameHi)), h("p", { class: "meta" }, `${w.agency} · ${w.scorecard.openIssues} ${L("open", "खुली")} · ${w.scorecard.openByPriority.P1} P1`))))));
    return;
  }
  const w = wards.find((x) => x.id === ward)!;
  const list = h("div", { class: "off-queue" });
  const box = h("div", { class: "off-detail card" }, h("p", { class: "muted" }, L("Pick an issue from the queue.", "कतार से समस्या चुनें।")));
  const refresh = async () => {
    let queue: IssueSummary[];
    try {
      queue = (await civicApi.queue(ward)).issues;
    } catch (err) {
      toast(err instanceof ApiFailure ? err.message : String(err), "error");
      return;
    }
    list.replaceChildren(...kids(
      h("div", { class: "q-head" }, h("span", {}, L("Issue", "समस्या")), h("span", {}, L("Priority", "प्राथमिकता")), h("span", {}, L("Reports", "रिपोर्ट")), h("span", {}, L("State", "स्थिति"))),
      ...queue.map((i) => {
        const row = btn(h("span", { class: "q-row-in" },
          h("span", { class: "q-issue" }, catBadge(i.category, i.priority), h("span", {}, h("b", {}, catLabel(i.category)), h("small", {}, i.place ?? i.issueId))),
          priorityChip(i.priority, i.score),
          h("span", {}, `${i.reports} · ${i.sources}👤`),
          h("span", { class: `wf wf-${i.workflowState.toLowerCase()}` }, wfLabel(i.workflowState),
            i.overdueDays > 0 ? h("small", { class: "overdue" }, ` ${i.overdueDays}${L("d late", " दिन देर")}`) : h("small", {}, " " + ago(i.openedAt)))),
          `q-row ${selected === i.issueId ? "sel" : ""}`, () => {
            selected = i.issueId;
            for (const r of list.querySelectorAll(".q-row")) r.classList.toggle("sel", r === row);
            void detail(box, i.issueId, queue, refresh);
          });
        return row;
      }),
      queue.length ? null : h("p", { class: "empty" }, L("Queue is empty. Nothing open in this ward.", "कतार खाली है।"))));
    if (selected && queue.some((q) => q.issueId === selected)) await detail(box, selected, queue, refresh);
    else if (selected) {
      selected = undefined;
      box.replaceChildren(h("p", { class: "muted" }, L("Done. Pick the next issue.", "हो गया। अगली समस्या चुनें।")));
    }
  };
  el.replaceChildren(h("div", { class: "page wide" },
    h("header", { class: "page-head row" },
      h("div", {}, h("p", { class: "eyebrow" }, `${w.agency} · ${L("signed in as ward officer (demo)", "वार्ड अधिकारी (डेमो)")}`),
        h("h1", {}, L(w.name, w.nameHi))),
      h("a", { class: "secondary", href: "#/officer/" }, L("Switch ward", "वार्ड बदलें"))),
    h("div", { class: "metrics" },
      h("div", { class: "metric p1" }, h("b", {}, String(w.scorecard.openByPriority.P1)), h("span", {}, "P1")),
      h("div", { class: "metric" }, h("b", {}, String(w.scorecard.openIssues)), h("span", {}, L("open", "खुली"))),
      h("div", { class: `metric ${w.scorecard.overdue ? "warn" : ""}` }, h("b", {}, String(w.scorecard.overdue)), h("span", {}, L("overdue", "देर")))),
    wardPulse(w.id, civicApi.pulse),
    h("div", { class: "off-layout" }, list, box)));
  await refresh();
}

export function resetOfficer(): void {
  ward = "";
}
