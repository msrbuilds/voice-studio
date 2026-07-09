// Pure SRT/VTT formatters for ASR segments. No DOM, no network — the backend
// returns timestamped segments and the client renders the subtitle file.

import type { AsrSegment } from "@/types/models";

/**
 * `1.24 -> "00:00:01,240"`. `sep` is "," for SRT and "." for WebVTT.
 *
 * Rounds to whole milliseconds ONCE, up front, then decomposes. Splitting the
 * seconds off first and flooring the remainder loses to binary float: 3.9 - 3
 * is 0.8999999999999995, which would emit ",899". Rounding the total also
 * keeps the millisecond field 3 digits — carrying into the seconds instead of
 * producing an invalid ",1000".
 */
export function formatTimestamp(seconds: number, sep: "," | "."): string {
  const totalMs = Math.round(Math.max(0, seconds) * 1000);
  const ms = totalMs % 1000;
  const totalSec = (totalMs - ms) / 1000;
  const hh = Math.floor(totalSec / 3600);
  const mm = Math.floor((totalSec % 3600) / 60);
  const ss = totalSec % 60;
  const p2 = (n: number) => String(n).padStart(2, "0");
  return `${p2(hh)}:${p2(mm)}:${p2(ss)}${sep}${String(ms).padStart(3, "0")}`;
}

export function segmentsToSrt(segments: AsrSegment[]): string {
  return segments
    .map((s, i) => {
      const from = formatTimestamp(s.start, ",");
      const to = formatTimestamp(s.end, ",");
      return `${i + 1}\n${from} --> ${to}\n${s.text}\n`;
    })
    .join("\n");
}

export function segmentsToVtt(segments: AsrSegment[]): string {
  const cues = segments
    .map((s) => {
      const from = formatTimestamp(s.start, ".");
      const to = formatTimestamp(s.end, ".");
      return `${from} --> ${to}\n${s.text}\n`;
    })
    .join("\n");
  return cues ? `WEBVTT\n\n${cues}` : "WEBVTT\n";
}
