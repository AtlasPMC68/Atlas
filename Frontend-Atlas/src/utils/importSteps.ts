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

export function zoneColorCount(inputs: ImportInputs): number {
  return (inputs.colors ?? []).filter((c) => c.kind === "zone").length;
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
    case "colors":
      return zoneColorCount(inputs) > 0;
  }
}

// Control points are matched against the framed area, so they wait for it.
// Everything else can be done in any order, and redone.
function isLocked(id: StepId, inputs: ImportInputs): boolean {
  return (id === "sift" || id === "cities") && !inputs.frameBounds;
}

const STEPS: { id: StepId; required: boolean }[] = [
  { id: "zone", required: true },
  { id: "legend", required: true },
  { id: "sift", required: true },
  { id: "cities", required: false },
  { id: "colors", required: true },
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

// Redoing the framing drops the points matched inside the old one.
export function zoneRedoResetsPoints(inputs: ImportInputs): boolean {
  return (inputs.controlPoints ?? []).length > 0;
}

// Merge a patch the way the backend does (services/imports.py): null clears a
// key, and a new framing box drops the control points unless the patch sets
// them. Used where the inputs live only in the browser (dev-test mode).
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
    JSON.stringify(next.frameBounds ?? null) !==
    JSON.stringify(current.frameBounds ?? null);
  if (frameChanged && !("controlPoints" in patch)) delete next.controlPoints;
  return next;
}
