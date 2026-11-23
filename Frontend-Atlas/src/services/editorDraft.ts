import type {
  EditorDraft,
  EditorDraftScope,
  EditorFormDrafts,
} from "../typescript/editorDraft";
import type { Feature } from "../typescript/feature";

const DATABASE_NAME = "atlas-editor-drafts";
const DATABASE_VERSION = 1;
const STORE_NAME = "drafts";
const PROJECT_INDEX = "projectId";

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isOptionalString(value: unknown): boolean {
  return value === undefined || typeof value === "string";
}

function isOptionalNumericInput(value: unknown): boolean {
  return value === undefined || typeof value === "string" ||
    (typeof value === "number" && Number.isFinite(value));
}

function isYearInput(value: unknown): boolean {
  return value === null || typeof value === "string" ||
    (typeof value === "number" && Number.isFinite(value));
}

function isCoordinates(value: unknown): boolean {
  return Array.isArray(value) && value.every((coordinate) =>
    Array.isArray(coordinate)
      ? isCoordinates(coordinate)
      : typeof coordinate === "number" && Number.isFinite(coordinate),
  );
}

function isFeatureList(value: unknown): value is Feature[] {
  return Array.isArray(value) && value.every((feature) =>
    isRecord(feature) && feature.type === "Feature" &&
    typeof feature.id === "string" && feature.id.length > 0 &&
    isRecord(feature.properties) && isRecord(feature.geometry) &&
    ["Point", "LineString", "Polygon", "MultiPoint", "MultiLineString", "MultiPolygon"]
      .includes(String(feature.geometry.type)) &&
    isCoordinates(feature.geometry.coordinates),
  );
}

function isForms(value: unknown): value is EditorFormDrafts {
  if (!isRecord(value)) return false;
  const edit = value.featureEdit;
  if (edit !== undefined && (!isRecord(edit) || typeof edit.featureId !== "string" ||
    typeof edit.name !== "string" || !isOptionalString(edit.labelText) ||
    !isOptionalString(edit.color) || !isOptionalString(edit.strokeColor) ||
    !isOptionalNumericInput(edit.opacity) || !isOptionalNumericInput(edit.strokeOpacity) ||
    !isOptionalNumericInput(edit.strokeWidth) ||
    !isFeatureEditPayload(edit.draft))) return false;

  const map = value.addMap;
  if (map !== undefined && (!isRecord(map) || typeof map.title !== "string" ||
    !isYearInput(map.startYear) || !isYearInput(map.endYear) ||
    typeof map.startDate !== "string" || typeof map.endDate !== "string" ||
    typeof map.usePreciseDates !== "boolean")) return false;

  const image = value.addImage;
  if (image !== undefined && (!isRecord(image) ||
    !(image.selectedFile === null ||
      (typeof File !== "undefined" && image.selectedFile instanceof File)))) return false;

  const project = value.createProject;
  return project === undefined || (isRecord(project) &&
    isOptionalString(project.title) && isOptionalString(project.description) &&
    typeof project.isPrivate === "boolean");
}

function isFeatureEditPayload(value: unknown): boolean {
  // Absent in older drafts, whose flat form fields are validated above.
  if (value === undefined) return true;
  if (!isRecord(value) || typeof value.name !== "string" ||
    typeof value.wordType !== "string" ||
    !["labelText", "colorHex", "textColorHex", "strokeColorHex", "labelStyleSelection"]
      .every((field) => isOptionalString(value[field])) ||
    !["textSizePx", "fillOpacity", "strokeOpacity", "strokeWidth"]
      .every((field) => isOptionalNumericInput(value[field])) ||
    !(value.customLabelStyleId === null || isOptionalString(value.customLabelStyleId)) ||
    !(value.selectedMapIds === undefined || (Array.isArray(value.selectedMapIds) &&
      value.selectedMapIds.every((id) => typeof id === "string")))) return false;
  const style = value.customLabelStyle;
  return style === undefined || style === null || (isRecord(style) &&
    typeof style.id === "string" && typeof style.name === "string" &&
    ["sizePx", "priority", "minZoom"].every((field) =>
      typeof style[field] === "number" && Number.isFinite(style[field])) &&
    ["normal", "italic"].includes(String(style.fontStyle)) &&
    ["none", "uppercase"].includes(String(style.textTransform)) &&
    isOptionalString(style.color));
}

function isScope(value: unknown): value is EditorDraftScope {
  return isRecord(value) && typeof value.projectId === "string" &&
    value.projectId.length > 0 && (value.subject === null ||
      (typeof value.subject === "string" && value.subject.length > 0));
}

export function isEditorDraft(value: unknown): value is EditorDraft {
  if (!isScope(value) || !isRecord(value)) return false;
  return value.version === 1 && typeof value.id === "string" && value.id.length > 0 &&
    typeof value.updatedAt === "number" && Number.isFinite(value.updatedAt) &&
    isFeatureList(value.features) && isFeatureList(value.baseFeatures) &&
    Array.isArray(value.visibility) && value.visibility.every((entry) =>
      Array.isArray(entry) && entry.length === 2 &&
      typeof entry[0] === "string" && typeof entry[1] === "boolean",
    ) &&
    Array.isArray(value.persistedFeatureIds) &&
    value.persistedFeatureIds.every((id) => typeof id === "string") &&
    Array.isArray(value.pendingDeletions) &&
    value.pendingDeletions.every((id) => typeof id === "string") &&
    isForms(value.forms) &&
    (value.intent === null || value.intent === "resume" || value.intent === "save") &&
    ["idle", "put-pending", "delete-pending"].includes(String(value.savePhase)) &&
    (value.targetProjectId === undefined ||
      (typeof value.targetProjectId === "string" && value.targetProjectId.length > 0));
}

function sameScope(value: unknown, scope: EditorDraftScope): boolean {
  return isRecord(value) && value.projectId === scope.projectId && value.subject === scope.subject;
}

function assertScope(scope: EditorDraftScope): void {
  if (!isScope(scope)) throw new Error("Le compte ou le projet du brouillon est invalide.");
}

function assertDraft(value: unknown): asserts value is EditorDraft {
  if (!isEditorDraft(value)) {
    throw new Error("Le brouillon est illisible ou utilise une version non prise en charge.");
  }
}

export function createEditorDraftId(): string {
  return crypto.randomUUID();
}

function snapshot<T>(value: T): T {
  if (typeof File !== "undefined" && value instanceof File) return value;
  if (Array.isArray(value)) return value.map(snapshot) as T;
  if (!isRecord(value)) return value;
  // Copy Vue proxies into plain data now, before awaiting IndexedDB or further user edits.
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, snapshot(item)])) as T;
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("Le stockage local des brouillons est indisponible."));
      return;
    }

    let blocked = false;
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      const store = database.createObjectStore(STORE_NAME, { keyPath: "id" });
      // Null is not a valid IndexedDB index key, so filter the subject after this lookup.
      store.createIndex(PROJECT_INDEX, "projectId", { unique: false });
    };
    request.onsuccess = () => {
      if (blocked) {
        request.result.close();
        return;
      }
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
    request.onerror = () => reject(request.error ?? new Error("Impossible d'ouvrir les brouillons locaux."));
    request.onblocked = () => {
      blocked = true;
      reject(new Error("Ferme les autres onglets Atlas pour ouvrir le stockage des brouillons."));
    };
  });
}

async function inTransaction<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore, setResult: (result: T) => void, fail: (error: unknown) => void) => void,
): Promise<T> {
  const database = await openDatabase();
  return new Promise<T>((resolve, reject) => {
    let result: T;
    let failure: unknown;
    let transaction: IDBTransaction;
    const fail = (error: unknown) => {
      failure = error;
      transaction.abort();
    };
    try {
      transaction = database.transaction(STORE_NAME, mode);
      transaction.oncomplete = () => {
        database.close();
        resolve(result);
      };
      transaction.onabort = () => {
        database.close();
        reject(failure ?? transaction.error ?? new Error("L'enregistrement local du brouillon a échoué."));
      };
      // Request errors abort the transaction by default; wait for that final outcome.
      run(transaction.objectStore(STORE_NAME), (value) => { result = value; }, fail);
    } catch (error) {
      database.close();
      reject(error);
    }
  });
}

export async function writeEditorDraft(draft: EditorDraft): Promise<void> {
  assertDraft(draft);
  // Pick the schema fields explicitly: authentication tokens never belong in this record.
  const record: EditorDraft = snapshot({
    version: 1,
    id: draft.id,
    projectId: draft.projectId,
    subject: draft.subject,
    updatedAt: draft.updatedAt,
    features: draft.features,
    visibility: draft.visibility,
    persistedFeatureIds: draft.persistedFeatureIds,
    pendingDeletions: draft.pendingDeletions,
    baseFeatures: draft.baseFeatures,
    forms: draft.forms,
    intent: draft.intent,
    savePhase: draft.savePhase,
    targetProjectId: draft.targetProjectId,
  });
  await inTransaction<void>("readwrite", (store, setResult, fail) => {
    const existing = store.get(draft.id);
    existing.onsuccess = () => {
      if (existing.result !== undefined && !sameScope(existing.result, draft)) {
        fail(new Error("Ce brouillon appartient à un autre compte ou projet."));
        return;
      }
      try {
        store.put(record);
        setResult(undefined);
      } catch (error) {
        fail(error);
      }
    };
  });
}

export async function readEditorDraft(id: string, scope: EditorDraftScope): Promise<EditorDraft | null> {
  assertScope(scope);
  return inTransaction<EditorDraft | null>("readonly", (store, setResult, fail) => {
    const request = store.get(id);
    request.onsuccess = () => {
      if (request.result === undefined || !sameScope(request.result, scope)) {
        setResult(null);
        return;
      }
      try {
        assertDraft(request.result);
        setResult(request.result);
      } catch (error) {
        fail(error);
      }
    };
  });
}

export async function listEditorDrafts(projectId: string, subject: string | null): Promise<EditorDraft[]> {
  const scope = { projectId, subject };
  assertScope(scope);
  return inTransaction<EditorDraft[]>("readonly", (store, setResult, fail) => {
    const request = store.index(PROJECT_INDEX).getAll(projectId);
    request.onsuccess = () => {
      try {
        const drafts = (request.result as unknown[]).filter((draft) => sameScope(draft, scope));
        drafts.forEach(assertDraft);
        setResult((drafts as EditorDraft[]).sort((left, right) => right.updatedAt - left.updatedAt));
      } catch (error) {
        fail(error);
      }
    };
  });
}

export async function deleteEditorDraft(id: string, scope: EditorDraftScope): Promise<void> {
  assertScope(scope);
  await inTransaction<void>("readwrite", (store, setResult, fail) => {
    const request = store.get(id);
    request.onsuccess = () => {
      if (request.result !== undefined && !sameScope(request.result, scope)) {
        fail(new Error("Ce brouillon appartient à un autre compte ou projet."));
        return;
      }
      try {
        store.delete(id);
        setResult(undefined);
      } catch (error) {
        fail(error);
      }
    };
  });
}

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (!isRecord(value)) return value;
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
}

function featureSignatures(features: Feature[]): string[] {
  return features.map((feature) => {
    const { createdAt, updatedAt, ...content } = feature;
    void createdAt;
    void updatedAt;
    return JSON.stringify(canonical(content));
  }).sort();
}

// Compare content, preserving geometry coordinate order, rather than server serialization order.
export function haveSameEditorFeatures(left: Feature[], right: Feature[]): boolean {
  return JSON.stringify(featureSignatures(left)) === JSON.stringify(featureSignatures(right));
}
