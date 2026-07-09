import { describe, expect, it } from "vitest";
import { isRtlText, textDirection } from "./textStats";

const URDU = "خوش آمدید! یہ آواز مکمل طور پر آپ کے اپنے کمپیوٹر پر بنائی جا رہی ہے۔";
const ARABIC = "مرحبا بالعالم";
const HEBREW = "שלום עולם";

describe("isRtlText", () => {
  it("detects RTL scripts", () => {
    expect(isRtlText(URDU)).toBe(true);
    expect(isRtlText(ARABIC)).toBe(true);
    expect(isRtlText(HEBREW)).toBe(true);
  });

  it("leaves Latin text LTR", () => {
    expect(isRtlText("Hello world")).toBe(false);
    expect(isRtlText("123 456 !?")).toBe(false);
  });

  it("is empty-safe", () => {
    expect(isRtlText("")).toBe(false);
    expect(isRtlText(null)).toBe(false);
    expect(isRtlText(undefined)).toBe(false);
  });

  it("uses a ratio, so a mostly-Urdu line with an English tag stays RTL", () => {
    expect(isRtlText(`${URDU} [en]`)).toBe(true);
  });

  it("treats a mostly-English line with one Urdu word as LTR", () => {
    expect(isRtlText("The Urdu word for welcome is خوش")).toBe(false);
  });
});

describe("textDirection", () => {
  it("maps to the dir attribute values", () => {
    expect(textDirection(URDU)).toBe("rtl");
    expect(textDirection("Hello")).toBe("ltr");
    expect(textDirection("")).toBe("ltr");
  });
});
