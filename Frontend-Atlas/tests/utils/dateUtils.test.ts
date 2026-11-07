import { describe, it, expect } from "vitest";
import {
  toYear,
  parseIsoDateUtc,
  toIsoDateUtc,
  yearToIsoStart,
  yearToIsoEnd,
} from "../../src/utils/dateUtils";

describe("dateUtils", () => {
  describe("toYear", () => {
    it("returns null for empty or invalid values", () => {
      expect(toYear(null)).toBeNull();
      expect(toYear(undefined)).toBeNull();
      expect(toYear("")).toBeNull();
      expect(toYear("invalid")).toBeNull();
      expect(toYear("1750")).toBeNull();
    });

    it("parses YYYY-MM-DD strings", () => {
      expect(toYear("1750-01-01")).toBe(1750);
      expect(toYear("1984-12-31")).toBe(1984);
    });

    it("parses ISO strings containing a time component", () => {
      expect(toYear("1750-01-01T00:00:00Z")).toBe(1750);
      expect(toYear("2026-05-15T14:30:00.000Z")).toBe(2026);
    });
  });

  describe("parseIsoDateUtc", () => {
    it("returns null for empty or invalid values", () => {
      expect(parseIsoDateUtc(null)).toBeNull();
      expect(parseIsoDateUtc(undefined)).toBeNull();
      expect(parseIsoDateUtc("")).toBeNull();
      expect(parseIsoDateUtc("invalid")).toBeNull();
    });

    it("parses YYYY-MM-DD into a UTC Date", () => {
      const date = parseIsoDateUtc("1750-06-15");
      expect(date).not.toBeNull();
      expect(date?.getUTCFullYear()).toBe(1750);
      expect(date?.getUTCMonth()).toBe(5); // 0-indexed: June
      expect(date?.getUTCDate()).toBe(15);
    });

    it("parses ISO strings with time into a UTC Date", () => {
      const date = parseIsoDateUtc("1750-06-15T12:00:00Z");
      expect(date).not.toBeNull();
      expect(date?.getUTCFullYear()).toBe(1750);
      expect(date?.getUTCMonth()).toBe(5);
      expect(date?.getUTCDate()).toBe(15);
    });
  });

  describe("toIsoDateUtc", () => {
    it("formats a Date to YYYY-MM-DD using UTC values", () => {
      const date = new Date(Date.UTC(1750, 0, 1));
      expect(toIsoDateUtc(date)).toBe("1750-01-01");
    });
  });

  describe("yearToIsoStart and yearToIsoEnd", () => {
    it("converts year to start and end dates", () => {
      expect(yearToIsoStart(1750)).toBe("1750-01-01");
      expect(yearToIsoEnd(1750)).toBe("1750-12-31");
    });

    it("pads 3-digit or fewer year numbers with leading zeros", () => {
      expect(yearToIsoStart(500)).toBe("0500-01-01");
      expect(yearToIsoEnd(500)).toBe("0500-12-31");
    });
  });
});
