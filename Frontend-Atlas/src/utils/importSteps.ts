import type { ControlPointInput } from "../typescript/georef";
import type {
  ImportInputs,
  ImportInputsPatch,
  StepId,
  StepState,
  StepStatus,
} from "../typescript/importSession";

// The backend's MIN_CONTROL_POINTS: an affine needs three points.
export const MIN_SIFT_POINTS = 3;

export function siftPoints(inputs: ImportInputs): ControlPointInput[] {
  return (inputs.controlPoints ?? []).filter((p) => p.source === "sift");
}

export function cityPoints(inputs: ImportInputs): ControlPointInput[] {
  return (inputs.controlPoints ?? []).filter((p) => p.source === "city");
}

export function checkPoints(inputs: ImportInputs): ControlPointInput[] {
  return inputs.checkPoints ?? [];
}

export function zoneColorCount(inputs: ImportInputs): number {
  return (inputs.colors ?? []).filter((c) => c.kind === "zone").length;
}

export function waterColorCount(inputs: ImportInputs): number {
  return (inputs.colors ?? []).filter((c) => c.kind === "water").length;
}

// Dev-test: the groups of inputs a new case can take from another case of the
// same map, so that what two cases do not vary is identical, not re-clicked.
export type CasePart =
  | "frame"
  | "legend"
  | "sift"
  | "cities"
  | "checks"
  | "zoneColors"
  | "waterColors";

// Points are matched inside a framing box: they only travel with it.
export const PARTS_NEEDING_FRAME: readonly CasePart[] = ["sift", "cities", "checks"];

export function casePartCount(inputs: ImportInputs, part: CasePart): number {
  switch (part) {
    case "frame":
      return inputs.frameBounds ? 1 : 0;
    case "legend":
      return inputs.legend ? 1 : 0;
    case "sift":
      return siftPoints(inputs).length;
    case "cities":
      return cityPoints(inputs).length;
    case "checks":
      return checkPoints(inputs).length;
    case "zoneColors":
      return zoneColorCount(inputs);
    case "waterColors":
      return waterColorCount(inputs);
  }
}

export function pickCaseInputs(source: ImportInputs, parts: Iterable<CasePart>): ImportInputs {
  const wanted = new Set(parts);
  if (!source.frameBounds || !wanted.has("frame")) {
    for (const part of PARTS_NEEDING_FRAME) wanted.delete(part);
  }

  const picked: ImportInputs = {};
  if (wanted.has("frame") && source.frameBounds) picked.frameBounds = source.frameBounds;
  if (wanted.has("legend") && source.legend) picked.legend = source.legend;

  const controlPoints = [
    ...(wanted.has("sift") ? siftPoints(source) : []),
    ...(wanted.has("cities") ? cityPoints(source) : []),
  ];
  if (controlPoints.length > 0) picked.controlPoints = controlPoints;
  if (wanted.has("checks") && checkPoints(source).length > 0) {
    picked.checkPoints = checkPoints(source);
  }

  const colors = (source.colors ?? []).filter(
    (c) =>
      (c.kind === "zone" && wanted.has("zoneColors")) ||
      (c.kind === "water" && wanted.has("waterColors")),
  );
  if (colors.length > 0) picked.colors = colors;
  return picked;
}

function isDone(id: StepId, inputs: ImportInputs): boolean {
  switch (id) {
    case "zone":
      return !!inputs.frameBounds;
    case "legend":
      return !!inputs.legend;
    case "sift":
      return siftPoints(inputs).length >= MIN_SIFT_POINTS;
    case "cities":
      return cityPoints(inputs).length > 0;
    case "checks":
      return checkPoints(inputs).length > 0;
    case "colors":
      return zoneColorCount(inputs) > 0;
    case "shapes":
      return (inputs.shapes ?? []).length > 0;
  }
}

// Control and check points are matched against the framed area, so they wait
// for it. Everything else can be done in any order, and redone.
function isLocked(id: StepId, inputs: ImportInputs): boolean {
  return (id === "sift" || id === "cities" || id === "checks") && !inputs.frameBounds;
}

const STEPS: { id: StepId; required: boolean }[] = [
  { id: "zone", required: true },
  { id: "legend", required: true },
  { id: "sift", required: true },
  { id: "cities", required: false },
  { id: "checks", required: false },
  { id: "colors", required: true },
  { id: "shapes", required: false },
];

export function deriveStepStates(inputs: ImportInputs): Record<StepId, StepState> {
  const states = {} as Record<StepId, StepState>;
  for (const { id, required } of STEPS) {
    let status: StepStatus = "available";
    if (isLocked(id, inputs)) status = "locked";
    else if (isDone(id, inputs)) status = "done";
    states[id] = { id, status, required };
  }
  return states;
}

// Required steps still to do, in checklist order.
export function missingRequiredSteps(inputs: ImportInputs): StepId[] {
  return STEPS.filter((s) => s.required && !isDone(s.id, inputs)).map((s) => s.id);
}

export function canStartExtraction(inputs: ImportInputs): boolean {
  return missingRequiredSteps(inputs).length === 0;
}

// Redoing the framing drops the points matched inside the old one. Framing
// for the first time drops nothing: no point was matched under a box that did
// not exist (a dev-test case made before the box existed).
export function zoneRedoResetsPoints(inputs: ImportInputs): boolean {
  const points = (inputs.controlPoints ?? []).length + checkPoints(inputs).length;
  return !!inputs.frameBounds && points > 0;
}

// Merge a patch the way the backend does (services/imports.py): null clears a
// key, and a *changed* framing box drops the control points unless the patch
// sets them; a first one keeps them. Used where the inputs live only in the
// browser (dev-test mode).
export function applyInputsPatch(
  current: ImportInputs,
  patch: ImportInputsPatch,
): ImportInputs {
  const merged: Record<string, unknown> = { ...current };
  for (const [key, value] of Object.entries(patch)) {
    if (value === null || value === undefined) delete merged[key];
    else merged[key] = value;
  }
  const next = merged as ImportInputs;
  const frameChanged =
    !!current.frameBounds &&
    JSON.stringify(next.frameBounds ?? null) !== JSON.stringify(current.frameBounds);
  if (frameChanged && !("controlPoints" in patch)) delete next.controlPoints;
  if (frameChanged && !("checkPoints" in patch)) delete next.checkPoints;
  return next;
}
