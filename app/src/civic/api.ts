/** Civic issue API: contracts mirror backend/src/civic.py. */
import { request } from "../flood/api.ts";

export type Category = "POTHOLE" | "WATERLOGGING" | "OPEN_MANHOLE" | "BLOCKED_ROAD" | "GARBAGE_DUMP" | "STREETLIGHT_OUT" | "OTHER";
export type EvidenceState = "UNKNOWN" | "REPORTED" | "CORROBORATED" | "CONFLICTED" | "STALE" | "CLEAR_REPORTED";
export type WorkflowState =
  | "OPEN" | "VERIFIED" | "ASSIGNED" | "IN_PROGRESS" | "RESOLVED" | "REOPENED"
  | "CLOSED" | "CLOSED_UNCONFIRMED" | "REJECTED" | "MERGED";
export type Priority = "P1" | "P2" | "P3";
export type Detail = "deep" | "wide" | "near_school" | "near_hospital" | "major_road" | "night_hazard" | "vehicles_stuck";

export interface IssueSummary {
  issueId: string;
  category: Category;
  label: string;
  labelHi: string;
  place: string | null;
  lat: number;
  lon: number;
  wardId: string;
  evidenceState: EvidenceState;
  workflowState: WorkflowState;
  score: number;
  priority: Priority;
  reports: number;
  sources: number;
  photos: number;
  openedAt: string;
  dueAt: string;
  overdueDays: number;
  blocksRoute: boolean;
  updatedAt: string;
  provenance: string;
  distanceM?: number;
  revision?: number;
}

export interface TimelineEntry {
  at: string;
  actor: "citizen" | "officer" | "community" | "system";
  action: string;
  label: string;
  note?: string | null;
  source: string | null;
  photoUrl: string | null;
}

export interface IssueDetail extends IssueSummary {
  revision: number;
  categoryInfo: { label: string; labelHi: string; owner: string; slaDays: number; routing: string; freshnessHours: number; radiusM: number };
  ward: { id: string; name: string; nameHi: string; agency: string } | null;
  evidence: { state: EvidenceState; reasonCode: string; positiveSources: number; negativeSources: number; totalSources: number; totalReports: number; photos: number };
  severity: { score: number; priority: Priority; parts: { code: string; label: string; points: number }[] };
  details: Detail[];
  workflow: { state: WorkflowState; since: string; assignee?: string | null; resolvedAt?: string | null; rejectReason?: string | null; mergedInto?: string | null; reopenCount?: number };
  observations: { kind: string; observedAt: string; source: string; details: string[]; photoUrl: string | null; description: string | null }[];
  timeline: TimelineEntry[];
}

export interface Scorecard {
  ward: { id: string; name: string; nameHi: string; agency: string };
  totalIssues: number;
  openIssues: number;
  openByPriority: Record<Priority, number>;
  overdue: number;
  medianDaysToResolve: number | null;
  citizenConfirmedFixes: number;
  closedUnconfirmed: number;
  reopens: number;
  confirmedFixRate: number | null;
  closedByCitizensOnly: number;
  byCategory: Record<Category, number>;
}

export interface Ward {
  id: string;
  name: string;
  nameHi: string;
  agency: string;
  centre: [number, number];
  radiusM: number;
  scorecard: Scorecard;
}

export interface Photo { contentType: "image/jpeg" | "image/webp"; data: string }

export interface ReportBody {
  schemaVersion: "1.0";
  eventId: string;
  category: Category;
  observedAt: string;
  location: { lat: number; lon: number; accuracyM?: number | null };
  description?: string;
  details?: Detail[];
  photo?: Photo;
  issueId?: string;
  place?: string;
  clientMode: string;
}

export interface WriteResult {
  eventId: string;
  duplicate: boolean;
  issueId: string;
  joined: boolean;
  revision: number;
  evidenceState: EvidenceState;
  workflowState: WorkflowState;
  priority: Priority;
  score: number;
  reports: number;
  sources: number;
}

export interface Draft {
  suggestedCategory: Category | null;
  suggestedDetails: Detail[];
  method: string;
  fallbackReason?: string | null;
}

const citizen = (id: string) => ({ "x-demo-contributor": id });
const officer = (ward: string) => ({ "x-demo-officer": ward });
const qs = (q: Record<string, string | undefined>) =>
  Object.entries(q).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v as string)}`).join("&");

export const civicApi = {
  issues: (q: { status?: string; category?: string; ward?: string; near?: string } = {}) =>
    request<{ generatedAt: string; count: number; issues: IssueSummary[]; provenance: string }>("GET", "/v1/issues?" + qs(q)),
  issue: (id: string) => request<IssueDetail>("GET", `/v1/issues/${encodeURIComponent(id)}`),
  report: (body: ReportBody, who: string) => request<WriteResult>("POST", "/v1/reports", body, citizen(who)),
  vote: (id: string, kind: "STILL_THERE" | "FIXED", clientMode: string, who: string) =>
    request<WriteResult>("POST", `/v1/issues/${encodeURIComponent(id)}/votes`, {
      schemaVersion: "1.0", eventId: crypto.randomUUID(), kind, observedAt: new Date().toISOString(), clientMode,
    }, citizen(who)),
  draft: (text: string, who: string) => request<Draft>("POST", "/v1/report-drafts", { text }, citizen(who)),
  wards: () => request<{ wards: Ward[]; note: string }>("GET", "/v1/wards"),
  queue: (ward: string) => request<{ ward: Ward; issues: IssueSummary[] }>("GET", `/v1/wards/${ward}/queue`, undefined, officer(ward)),
  transition: (id: string, ward: string, body: Record<string, unknown>) =>
    request<IssueDetail>("POST", `/v1/issues/${encodeURIComponent(id)}/transitions`, body, officer(ward)),
  reset: (key: string) => request("POST", "/v1/demo/control", { reset: true }, { "x-demo-admin-key": key }),
};
