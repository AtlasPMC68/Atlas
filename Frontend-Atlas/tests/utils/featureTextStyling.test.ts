import { describe, it, expect } from "vitest";
import {
  coerceEditedFeature,
  normalizeOpacity,
  normalizeStrokeWidth,
  prepareFeatureForEdit,
  MAX_STROKE_WIDTH_PX,
} from "../../src/utils/featureTextEditing";
import {
  formatLabelHtml,
  getLabelPresentation,
  normalizeTextSizePx,
} from "../../src/utils/labelPresentation";
import { camelToSnake, snakeToCamel } from "../../src/utils/utils";
import type { Feature } from "../../src/typescript/feature";

const city: Feature = {
  type: "Feature",
  id: "city-1",
  projectId: "project-1",
  mapId: "map-1",
  name: "Québec",
  geometry: { type: "Point", coordinates: [-71.2, 46.8] },
  properties: {
    name: "Québec",
    labelText: "Québec",
    mapElementType: "point",
    rawType: "city",
    colorRgb: [0, 0, 0],
  },
  createdAt: "2026-01-01",
  updatedAt: "2026-01-01",
};

const province: Feature = {
  ...city,
  id: "province-1",
  name: "QUÉBEC",
  properties: {
    name: "QUÉBEC",
    labelText: "QUÉBEC",
    mapElementType: "label",
    rawType: "province",
    colorRgb: [0, 0, 0],
  },
};

describe("normalizeOpacity", () => {
  it("keeps a value already in range, as a number", () => {
    expect(normalizeOpacity(0.4)).toBe(0.4);
    expect(normalizeOpacity("0.4")).toBe(0.4);
  });

  it("clamps to [0, 1]", () => {
    expect(normalizeOpacity(5)).toBe(1);
    expect(normalizeOpacity(-2)).toBe(0);
  });

  it("returns undefined when there is no usable value", () => {
    expect(normalizeOpacity("")).toBeUndefined();
    expect(normalizeOpacity(undefined)).toBeUndefined();
    expect(normalizeOpacity("abc")).toBeUndefined();
  });
});

describe("normalizeStrokeWidth", () => {
  it("clamps to a drawable width", () => {
    expect(normalizeStrokeWidth(-1)).toBe(0);
    expect(normalizeStrokeWidth("3")).toBe(3);
    expect(normalizeStrokeWidth(9999)).toBe(MAX_STROKE_WIDTH_PX);
    expect(normalizeStrokeWidth("")).toBeUndefined();
  });
});

describe("normalizeTextSizePx", () => {
  it("rounds and clamps to the supported sizes", () => {
    expect(normalizeTextSizePx("17.6")).toBe(18);
    expect(normalizeTextSizePx(2)).toBe(6);
    expect(normalizeTextSizePx(500)).toBe(96);
    expect(normalizeTextSizePx("")).toBeUndefined();
  });
});

describe("editing the text style of an element", () => {
  it("opens a point with the text colour following its symbol and the size of its type", () => {
    const { draft } = prepareFeatureForEdit(city);
    expect(draft.colorHex).toBe("#000000");
    expect(draft.textColorHex).toBe("#000000");
    expect(draft.textSizePx).toBe(12);
  });

  it("opens a point with an opaque outline when none is stored", () => {
    expect(prepareFeatureForEdit(city).draft.strokeOpacity).toBe(1);
    expect(
      prepareFeatureForEdit({
        ...city,
        properties: { ...city.properties, strokeOpacity: 0.3 },
      }).draft.strokeOpacity,
    ).toBe(0.3);
    // A label has no symbol, so nothing is made up for it.
    expect(prepareFeatureForEdit(province).draft.strokeOpacity).toBeUndefined();
  });

  it("stores the text colour of a point only when it differs from the symbol", () => {
    const { draft } = prepareFeatureForEdit(city);

    const sameColour = coerceEditedFeature(city, { ...draft, colorHex: "#ff0000", textColorHex: "#ff0000" });
    expect(sameColour.properties.colorRgb).toEqual([255, 0, 0]);
    expect(sameColour.properties.textColorRgb).toBeUndefined();

    const ownColour = coerceEditedFeature(city, { ...draft, colorHex: "#ffee00", textColorHex: "#000000" });
    expect(ownColour.properties.colorRgb).toEqual([255, 238, 0]);
    expect(ownColour.properties.textColorRgb).toEqual([0, 0, 0]);
    expect(getLabelPresentation(ownColour).colorCss).toBe("rgb(0, 0, 0)");
  });

  it("gives a label a single colour", () => {
    const { draft } = prepareFeatureForEdit(province);
    const edited = coerceEditedFeature(province, { ...draft, colorHex: "#00ff00", textColorHex: "#0000ff" });
    expect(edited.properties.colorRgb).toEqual([0, 255, 0]);
    expect(edited.properties.textColorRgb).toBeUndefined();
    expect(getLabelPresentation(edited).colorCss).toBe("rgb(0, 255, 0)");
  });

  it("stores a text size only when it leaves the size of the word type", () => {
    const { draft } = prepareFeatureForEdit(city);

    const untouched = coerceEditedFeature(city, { ...draft });
    expect(untouched.properties.textSizePx).toBeUndefined();
    expect(getLabelPresentation(untouched).sizePx).toBe(12);

    const larger = coerceEditedFeature(city, { ...draft, textSizePx: 30 });
    expect(larger.properties.textSizePx).toBe(30);
    expect(getLabelPresentation(larger).sizePx).toBe(30);

    // Reopened, the dialog shows the stored size.
    expect(prepareFeatureForEdit(larger).draft.textSizePx).toBe(30);
  });

  it("clamps what the form sends for the symbol", () => {
    const { draft } = prepareFeatureForEdit(city);
    const edited = coerceEditedFeature(city, {
      ...draft,
      fillOpacity: 12,
      strokeOpacity: "0.25" as unknown as number,
      strokeWidth: -4,
    });
    expect(edited.properties.fillOpacity).toBe(1);
    expect(edited.properties.strokeOpacity).toBe(0.25);
    expect(edited.properties.strokeWidth).toBe(0);
  });

  it("keeps the text style through a save and reload", () => {
    const { draft } = prepareFeatureForEdit(city);
    const edited = coerceEditedFeature(city, {
      ...draft,
      colorHex: "#ffee00",
      textColorHex: "#102030",
      textSizePx: 20,
      labelText: "Québec\nla capitale",
    });
    const reloaded = snakeToCamel(
      JSON.parse(JSON.stringify(camelToSnake(edited))),
    ) as Feature;
    const presentation = getLabelPresentation(reloaded);
    expect(presentation.colorCss).toBe("rgb(16, 32, 48)");
    expect(presentation.sizePx).toBe(20);
    expect(presentation.html).toBe("Québec<br>la Capitale");
  });
});

describe("formatLabelHtml", () => {
  it("balances a long single line over two lines", () => {
    expect(formatLabelHtml("Nouvelle-Orléans")).toBe("Nouvelle-<br>Orléans");
  });

  it("keeps the line breaks the author typed, without adding any", () => {
    expect(formatLabelHtml("Territoire contesté\nen 1783")).toBe(
      "Territoire contesté<br>en 1783",
    );
  });

  it("keeps an empty line between two paragraphs", () => {
    expect(formatLabelHtml("Un\n\nDeux")).toBe("Un<br><br>Deux");
  });

  it("escapes markup", () => {
    expect(formatLabelHtml("<b>A</b>\nB & C")).toBe("&lt;b&gt;A&lt;/b&gt;<br>B &amp; C");
  });
});
