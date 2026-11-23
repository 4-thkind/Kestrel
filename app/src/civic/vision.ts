/** Kestrel Vision: one small on-device model, many questions.
 * A distilled MobileNetV3 student turns a photo into an embedding; text heads (pre-computed offline)
 * turn the embedding into answers. Loaded only when a photo is involved; photos never leave the phone
 * for this. Every answer is a suggestion the person can override. */
import * as ort from "onnxruntime-web/webgpu";

import { classify, scoreLabels, similarity, type Guess, type Heads } from "./visionMath.ts";

const MODEL = "/models/kestrel-vision.onnx";
const HEADS = "/models/kestrel-vision-heads.json";

let ready: Promise<{ session: ort.InferenceSession; heads: Heads }> | undefined;

function load() {
  ready ??= Promise.all([
    ort.InferenceSession.create(MODEL, { executionProviders: ["wasm"] }),
    fetch(HEADS).then((r) => {
      if (!r.ok) throw new Error("vision heads missing");
      return r.json() as Promise<Heads>;
    }),
  ]).then(([session, heads]) => ({ session, heads }));
  ready.catch(() => (ready = undefined)); // a failed load (offline) may be retried later
  return ready;
}

/** Resize the shorter side to 224 and centre-crop, as in training; RGB 0..1, channels first. */
function pixels(img: HTMLImageElement | ImageBitmap): Float32Array {
  const size = 224;
  const w = img.width, h = img.height;
  const side = Math.min(w, h);
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, (w - side) / 2, (h - side) / 2, side, side, 0, 0, size, size);
  const px = ctx.getImageData(0, 0, size, size).data;
  const plane = size * size;
  const out = new Float32Array(3 * plane);
  for (let i = 0; i < plane; i++) for (let c = 0; c < 3; c++) out[c * plane + i] = px[i * 4 + c] / 255;
  return out;
}

export async function loadImage(src: string): Promise<HTMLImageElement> {
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.src = src;
  await img.decode();
  return img;
}

export async function embed(img: HTMLImageElement | ImageBitmap): Promise<Float32Array> {
  const { session } = await load();
  const out = await session.run({ image: new ort.Tensor("float32", pixels(img), [1, 3, 224, 224]) });
  return out.embedding.data as Float32Array;
}

export interface Reading {
  guess: Guess;
  preselect: boolean;                       // confident enough to pre-fill the category
  potholeLarge: number | null;              // P(large) when the photo looks like a pothole
  face: number;                             // P(face close-up): suggest retaking for privacy
  embedding: Float32Array;
}

/** Everything the report flow wants to know about one photo. */
export async function read(img: HTMLImageElement | ImageBitmap): Promise<Reading> {
  const { heads } = await load();
  const embedding = await embed(img);
  const guess = classify(embedding, heads);
  return {
    guess,
    preselect: guess.category !== null && guess.confidence >= heads.preselectThreshold,
    potholeLarge: guess.key === "pothole" ? scoreLabels(embedding, heads.extra.pothole_size, heads).large : null,
    face: scoreLabels(embedding, heads.extra.privacy, heads).face,
    embedding,
  };
}

/** After-photo check: probability that the site still shows a problem. Uses the main classifier
 * (P of any problem class among street photos), which scored 93% on the test split; a separate
 * "repaired road" prompt head scored 85% and was dropped. */
export async function stillThere(img: HTMLImageElement): Promise<number> {
  const { heads } = await load();
  const probs = Object.fromEntries(classify(await embed(img), heads).ranked.map((r) => [r.key, r.p]));
  const street = 1 - (probs.not_street ?? 0);
  const problem = heads.classes.filter((c) => c.category !== null).reduce((s, c) => s + (probs[c.key] ?? 0), 0);
  return street > 0 ? problem / street : 0;
}

/** Whether two photos show the same spot, using the threshold measured in ml/evaluate_vision.py. */
export async function sameSpot(a: Float32Array, b: Float32Array): Promise<boolean> {
  const { heads } = await load();
  return similarity(a, b, heads.dims) >= heads.sameSpotThreshold;
}
