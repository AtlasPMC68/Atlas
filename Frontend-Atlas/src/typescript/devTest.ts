import type { MultiPolygon, Polygon } from "geojson";
import type { ImportInputs } from "./importSession";

export type DevTestKind = "regression" | "probe";

// GET /dev-test-api/test-cases/{testId}/{caseId}/inputs
export interface DevTestCaseInputsResponse {
  testCaseId: string;
  testCase: string;
  kind: DevTestKind | null;
  imageUrl: string;
  imageFilename: string;
  inputs: ImportInputs;
}

// A stored dev-test case reopened to supply or change its inputs. Saving
// writes back to the same case, so its name and kind travel with it.
export interface EditedDevTestCase {
  id: string;
  name: string;
  kind: DevTestKind | null;
}

// An expected zone's outline: one or several polygons, holes kept.
export type ZoneGeometry = Polygon | MultiPolygon;

// A country in the border files (app/geojson/borders/, indexed by the backend).
export interface BorderCountry {
  code: string;
  name: string;
  hasOutline: boolean;
  regionCount: number;
}

export interface BorderRegion {
  id: string;
  name: string;
  // The unit grouping it (an Italian region for a province), when the file has one.
  group: string | null;
}

// One zone loaded from the border files: a country, or several regions merged.
export interface LoadedBorderZone {
  name: string;
  geometry: ZoneGeometry;
}
