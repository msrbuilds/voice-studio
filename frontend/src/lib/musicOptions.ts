export interface Opt {
  value: string;
  label: string;
}

const NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

// "auto" sentinel = let the model decide (submitted as "").
export const KEY_OPTIONS: Opt[] = [
  { value: "auto", label: "Auto" },
  ...NOTES.flatMap((n) => [
    { value: `${n} major`, label: `${n} major` },
    { value: `${n} minor`, label: `${n} minor` },
  ]),
];

export const TIMESIG_OPTIONS: Opt[] = [
  { value: "auto", label: "Auto" },
  { value: "4/4", label: "4/4" },
  { value: "3/4", label: "3/4" },
  { value: "2/4", label: "2/4" },
  { value: "6/8", label: "6/8" },
];

// UI "4/4" → numerator "4"; "auto" → "".
export function timeSigToNumerator(v: string): string {
  if (!v || v === "auto") return "";
  return v.split("/")[0] ?? "";
}

export function keyToParam(v: string): string {
  return !v || v === "auto" ? "" : v;
}

// Reverse mappers for applying an LM blueprint back into the buffer.
export function numeratorToTimeSig(n: string): string {
  const m: Record<string, string> = { "4": "4/4", "3": "3/4", "2": "2/4", "6": "6/8" };
  return m[(n ?? "").trim()] ?? "auto";
}

export function normalizeKey(k: string): string {
  const t = (k || "").trim();
  if (!t) return "auto";
  const parts = t.split(/\s+/);
  if (parts.length < 2) return "auto";
  const cand = `${parts[0]} ${parts[1]!.toLowerCase()}`; // "C Minor" → "C minor"
  return KEY_OPTIONS.some((o) => o.value === cand) ? cand : "auto";
}
