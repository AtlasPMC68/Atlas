import { describe, it, expect } from "vitest";
import {
  createFeaturesForSelectedMaps,
  coerceEditedFeature,
  prepareFeatureForEdit,
  applyCustomLabelStyleToFeature,
  removeCustomLabelStyleFromFeature,
  getWordTypePreviewStyle,
} from "../../src/utils/featureTextEditing";
import type { Feature } from "../../src/typescript/feature";
import type { CustomLabelStyle } from "../../src/utils/labelPresentation";

describe("featureTextEditing", () => {
  const basePointFeature: Feature = {
    type: "Feature",
    id: "f-point-1",
    mapId: "map-1",
    geometry: { type: "Point", coordinates: [-71.2, 46.8] },
    properties: {
      name: "Québec",
      mapElementType: "point",
      colorRgb: [0, 0, 0],
    },
  };

  const baseZoneFeature: Feature = {
    type: "Feature",
    id: "f-zone-1",
    mapId: "map-1",
    geometry: {
      type: "Polygon",
      coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]],
    },
    properties: {
      name: "Zone Principale",
      mapElementType: "zone",
      colorRgb: [255, 0, 0],
      strokeColor: [0, 0, 255],
      fillOpacity: 0.5,
      strokeOpacity: 0.8,
      strokeWidth: 2,
    },
  };

  const sampleCustomStyle: CustomLabelStyle = {
    id: "style-capital",
    name: "Capitale",
    sizePx: 18,
    fontStyle: "normal",
    fontWeight: "bold",
    textTransform: "uppercase",
    color: "#e11d48",
    priority: 80,
    minZoom: 2,
    mapElementType: "point",
  };

  describe("createFeaturesForSelectedMaps", () => {
    it("returns array with base feature if selectedMapIds is undefined or empty", () => {
      const resUndefined = createFeaturesForSelectedMaps(basePointFeature, undefined);
      expect(resUndefined).toHaveLength(1);
      expect(resUndefined[0]).toBe(basePointFeature);

      const resEmpty = createFeaturesForSelectedMaps(basePointFeature, []);
      expect(resEmpty).toHaveLength(1);
      expect(resEmpty[0]).toBe(basePointFeature);
    });

    it("returns array with base feature if single map selected", () => {
      const res = createFeaturesForSelectedMaps(basePointFeature, ["map-1"]);
      expect(res).toHaveLength(1);
      expect(res[0]).toBe(basePointFeature);
    });

    it("clones feature for each map when multiple maps selected", () => {
      const res = createFeaturesForSelectedMaps(basePointFeature, ["map-1", "map-2", "map-3"]);
      expect(res).toHaveLength(3);

      expect(res[0].id).toBe("f-point-1");
      expect(res[0].mapId).toBe("map-1");

      expect(res[1].id).not.toBe("f-point-1");
      expect(res[1].mapId).toBe("map-2");
      expect(res[1].properties.mapId).toBe("map-2");
      expect(res[1].properties.name).toBe("Québec");

      expect(res[2].id).not.toBe("f-point-1");
      expect(res[2].id).not.toBe(res[1].id);
      expect(res[2].mapId).toBe("map-3");
      expect(res[2].properties.mapId).toBe("map-3");
    });
  });

  describe("prepareFeatureForEdit", () => {
    it("prepares edit state and draft values for a point text feature", () => {
      const state = prepareFeatureForEdit(basePointFeature);
      expect(state.feature).toBe(basePointFeature);
      expect(state.draft.name).toBe("Québec");
      expect(state.draft.wordType).toBe("city");
      expect(state.draft.colorHex).toBe("#000000");
    });

    it("prepares opacity and stroke values for a zone feature", () => {
      const state = prepareFeatureForEdit(baseZoneFeature);
      expect(state.draft.name).toBe("Zone Principale");
      expect(state.draft.fillOpacity).toBe(0.5);
      expect(state.draft.strokeOpacity).toBe(0.8);
      expect(state.draft.strokeWidth).toBe(2);
      expect(state.draft.colorHex).toBe("#ff0000");
      expect(state.draft.strokeColorHex).toBe("#0000ff");
    });
  });

  describe("coerceEditedFeature", () => {
    it("updates text styling according to wordType and selected maps", () => {
      const edited = coerceEditedFeature(basePointFeature, {
        name: "fleuve saint-laurent",
        wordType: "river",
        colorHex: "#0284c7",
        selectedMapIds: ["map-10"],
      });

      expect(edited.name).toBe("Fleuve Saint-Laurent");
      expect(edited.mapId).toBe("map-10");
      expect(edited.properties.mapId).toBe("map-10");
      expect(edited.properties.colorRgb).toEqual([2, 132, 199]);
      expect(edited.properties.rawType).toBe("river");
    });

    it("applies custom label style and uppercase transformation when selected", () => {
      const edited = coerceEditedFeature(basePointFeature, {
        name: "ottawa",
        wordType: "city",
        customLabelStyleId: "style-capital",
        customLabelStyle: sampleCustomStyle,
        colorHex: "#e11d48",
      });

      expect(edited.properties.labelText).toBe("OTTAWA");
      expect(edited.properties.customLabelStyleId).toBe("style-capital");
      expect(edited.properties.sizePx).toBe(18);
      expect(edited.properties.fontWeight).toBe("bold");
    });

    it("updates non-text features (opacity, stroke, strokeWidth)", () => {
      const edited = coerceEditedFeature(baseZoneFeature, {
        name: "Nouvelle Zone",
        wordType: "city",
        colorHex: "#00ff00",
        strokeColorHex: "#000000",
        fillOpacity: 0.9,
        strokeOpacity: 1.0,
        strokeWidth: 4,
        selectedMapIds: ["map-2"],
      });

      expect(edited.name).toBe("Nouvelle Zone");
      expect(edited.mapId).toBe("map-2");
      expect(edited.properties.fillOpacity).toBe(0.9);
      expect(edited.properties.strokeOpacity).toBe(1.0);
      expect(edited.properties.strokeWidth).toBe(4);
      expect(edited.properties.colorRgb).toEqual([0, 255, 0]);
      expect(edited.properties.strokeColor).toEqual([0, 0, 0]);
    });
  });

  describe("applyCustomLabelStyleToFeature & removeCustomLabelStyleFromFeature", () => {
    it("attaches custom style and restores default when removed", () => {
      const withCustom = applyCustomLabelStyleToFeature(
        basePointFeature,
        sampleCustomStyle,
        "city",
        "Québec",
        "Québec",
      );

      expect(withCustom.properties.customLabelStyleId).toBe("style-capital");
      expect(withCustom.properties.customLabelStyle).toEqual(sampleCustomStyle);

      const restored = removeCustomLabelStyleFromFeature(withCustom);
      expect(restored.properties.customLabelStyleId).toBeNull();
      expect(restored.properties.customLabelStyle).toBeNull();
      expect(restored.properties.customLabelStyleFallbackWordType).toBeUndefined();
    });
  });

  describe("getWordTypePreviewStyle", () => {
    it("returns CSS styling preview for city and country word types", () => {
      const cityPreview = getWordTypePreviewStyle("city", "#123456");
      expect(cityPreview.color).toBe("#123456");
      expect(cityPreview.fontSize).toBeDefined();

      const countryPreview = getWordTypePreviewStyle("country");
      expect(countryPreview.textTransform).toBe("uppercase");
    });
  });
});
