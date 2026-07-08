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

// UI "4/4" → ACE-Step numerator "4"; "auto" → "".
export function timeSigToNumerator(v: string): string {
  if (!v || v === "auto") return "";
  return v.split("/")[0] ?? "";
}

export function keyToParam(v: string): string {
  return !v || v === "auto" ? "" : v;
}
