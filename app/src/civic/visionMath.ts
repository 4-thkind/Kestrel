/** Kestrel Vision maths: pure functions over embeddings and text heads, shared by the app and its self-check.
 * An embedding is [RN50-space half | ViT-B/16-space half], each half unit length (see ml/distill_student.py). */

export interface Heads {
  version: string;
  dims: [number, number];
  scale: number;
  preselectThreshold: number;
  sameSpotThreshold: number;
  classes: { key: string; category: string | null }[];
  classVectors: Record<string, number[]>;
  classBias?: Record<string, number>;
  extra: Record<string, Record<string, number[]>>;
}

/** Average of the two halves' cosine similarities: 1 = same direction, 0 = unrelated. */
export function similarity(a: ArrayLike<number>, b: ArrayLike<number>, dims: [number, number]): number {
  let s0 = 0;
  let s1 = 0;
  for (let i = 0; i < dims[0]; i++) s0 += a[i] * b[i];
  for (let i = dims[0]; i < dims[0] + dims[1]; i++) s1 += a[i] * b[i];
  return (s0 + s1) / 2;
}

/** Softmax over labels of scale × similarity, exactly as ml/evaluate_vision.py scores them. */
export function scoreLabels(emb: ArrayLike<number>, vectors: Record<string, number[]>, heads: Pick<Heads, "dims" | "scale">,
  bias: Record<string, number> = {}): Record<string, number> {
  const keys = Object.keys(vectors);
  const logits = keys.map((k) => heads.scale * similarity(emb, vectors[k], heads.dims) + (bias[k] ?? 0));
  const max = Math.max(...logits);
  const exps = logits.map((l) => Math.exp(l - max));
  const sum = exps.reduce((a, b) => a + b, 0);
  return Object.fromEntries(keys.map((k, i) => [k, exps[i] / sum]));
}

export interface Guess {
  key: string;                 // visual class, e.g. "pothole", "manhole_cover", "not_street"
  category: string | null;     // Kestrel category to report, or null when there is nothing to report
  confidence: number;
  ranked: { key: string; p: number }[];
}

export function classify(emb: ArrayLike<number>, heads: Heads): Guess {
  const probs = scoreLabels(emb, heads.classVectors, heads, heads.classBias);
  const ranked = Object.entries(probs).map(([key, p]) => ({ key, p })).sort((a, b) => b.p - a.p);
  const top = ranked[0];
  return { key: top.key, category: heads.classes.find((c) => c.key === top.key)?.category ?? null, confidence: top.p, ranked };
}
