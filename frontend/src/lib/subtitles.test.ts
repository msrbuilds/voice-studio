import { describe, expect, it } from "vitest";
import { formatTimestamp, segmentsToSrt, segmentsToVtt } from "./subtitles";
import type { AsrSegment } from "@/types/models";

const SEGS: AsrSegment[] = [
  { start: 1.24, end: 3.9, text: "Hello there" },
  { start: 3.9, end: 7.005, text: "General Kenobi" },
];

describe("formatTimestamp", () => {
  it("renders SRT comma form", () => {
    expect(formatTimestamp(0, ",")).toBe("00:00:00,000");
    expect(formatTimestamp(1.24, ",")).toBe("00:00:01,240");
    expect(formatTimestamp(7.005, ",")).toBe("00:00:07,005");
  });

  it("renders VTT dot form", () => {
    expect(formatTimestamp(1.24, ".")).toBe("00:00:01.240");
  });

  it("handles hours and minutes", () => {
    expect(formatTimestamp(3661.5, ",")).toBe("01:01:01,500");
    expect(formatTimestamp(59.999, ",")).toBe("00:00:59,999");
  });

  it("clamps negatives to zero rather than emitting garbage", () => {
    expect(formatTimestamp(-1, ",")).toBe("00:00:00,000");
  });

  it("never emits a 4-digit millisecond field", () => {
    // 59.9996s rounds to 60000ms; it must carry into the seconds rather than
    // rendering the invalid "00:00:59,1000".
    expect(formatTimestamp(59.9996, ",")).toBe("00:01:00,000");
  });

  it("survives binary float error (3.9 - 3 === 0.8999999999999995)", () => {
    expect(formatTimestamp(3.9, ",")).toBe("00:00:03,900");
    expect(formatTimestamp(7.005, ",")).toBe("00:00:07,005");
  });
});

describe("segmentsToSrt", () => {
  it("numbers cues from 1 and separates with a blank line", () => {
    expect(segmentsToSrt(SEGS)).toBe(
      "1\n00:00:01,240 --> 00:00:03,900\nHello there\n\n" +
        "2\n00:00:03,900 --> 00:00:07,005\nGeneral Kenobi\n",
    );
  });

  it("returns an empty string for no segments", () => {
    expect(segmentsToSrt([])).toBe("");
  });
});

describe("segmentsToVtt", () => {
  it("emits the WEBVTT header and dot-form timestamps", () => {
    expect(segmentsToVtt(SEGS)).toBe(
      "WEBVTT\n\n" +
        "00:00:01.240 --> 00:00:03.900\nHello there\n\n" +
        "00:00:03.900 --> 00:00:07.005\nGeneral Kenobi\n",
    );
  });

  it("still emits a valid header with no segments", () => {
    expect(segmentsToVtt([])).toBe("WEBVTT\n");
  });
});
