import { afterEach, describe, expect, it, vi } from "vitest";
import { reactive } from "vue";
import {
  deleteEditorDraft,
  haveSameEditorFeatures,
  isEditorDraft,
  listEditorDrafts,
  readEditorDraft,
  writeEditorDraft,
} from "../../src/services/editorDraft";
import type { EditorDraft } from "../../src/typescript/editorDraft";
import type { Feature } from "../../src/typescript/feature";

function makeFeature(id = "feature-1"): Feature {
  return {
    id,
    type: "Feature",
    projectId: "project-1",
    geometry: { type: "Point", coordinates: [10, 20] },
    properties: { name: "Avant", mapElementType: "point" },
    name: "Avant",
    createdAt: "2026-11-01T12:00:00Z",
    updatedAt: "2026-11-01T12:00:00Z",
  };
}

function makeDraft(overrides: Partial<EditorDraft> = {}): EditorDraft {
  return {
    version: 1,
    id: "draft-1",
    projectId: "project-1",
    subject: "account-1",
    updatedAt: 100,
    features: [makeFeature()],
    visibility: [["feature-1", false]],
    persistedFeatureIds: ["feature-1", "deleted-feature"],
    pendingDeletions: ["deleted-feature"],
    baseFeatures: [makeFeature(), makeFeature("deleted-feature")],
    forms: {},
    intent: "resume",
    savePhase: "idle",
    ...overrides,
  };
}

// This deliberately small fake checks our transaction/ownership handling, not browser storage.
function mockDatabase(initial: unknown[] = []) {
  const rows = new Map(initial.map((row) => [(row as EditorDraft).id, row]));
  let pendingWrites: (() => void)[] = [];
  function request(result: unknown) {
    const resultRequest = { result, onsuccess: null as (() => void) | null };
    queueMicrotask(() => resultRequest.onsuccess?.());
    return resultRequest;
  }
  const store = {
    get: vi.fn((id: string) => request(rows.get(id))),
    put: vi.fn((row: EditorDraft) => {
      pendingWrites.push(() => rows.set(row.id, row));
      return request(row.id);
    }),
    delete: vi.fn((id: string) => {
      pendingWrites.push(() => rows.delete(id));
      return request(undefined);
    }),
    index: vi.fn(() => ({
      getAll: vi.fn((projectId: string) => request([...rows.values()].filter(
        (row) => (row as EditorDraft).projectId === projectId,
      ))),
    })),
  };
  const transaction = {
    error: null as DOMException | null,
    oncomplete: null as (() => void) | null,
    onabort: null as (() => void) | null,
    objectStore: vi.fn(() => store),
    abort: vi.fn(() => {
      pendingWrites = [];
      queueMicrotask(() => transaction.onabort?.());
    }),
  };
  const database = {
    close: vi.fn(),
    onversionchange: null,
    transaction: vi.fn(() => transaction),
  };
  vi.stubGlobal("indexedDB", { open: vi.fn(() => request(database)) });
  return {
    rows,
    store,
    transaction,
    complete: () => {
      pendingWrites.forEach((write) => write());
      pendingWrites = [];
      transaction.oncomplete?.();
    },
  };
}

async function flushRequests() {
  for (let count = 0; count < 5; count += 1) await Promise.resolve();
}

afterEach(() => vi.unstubAllGlobals());

describe("editor draft schema", () => {
  it("preserves unfinished form input and rejects unsupported or malformed drafts", () => {
    const draft = makeDraft({
      forms: {
        featureEdit: { featureId: "feature-1", name: "Nom saisi", opacity: "" },
        addMap: {
          title: "Carte à créer", startYear: "", endYear: 2040,
          startDate: "", endDate: "", usePreciseDates: false,
        },
        addImage: { selectedFile: new File(["image"], "carte.png", { type: "image/png" }) },
        createProject: { title: "Copie", description: "Saisie", isPrivate: true },
      },
    });
    expect(isEditorDraft(draft)).toBe(true);
    expect(isEditorDraft({ ...draft, version: 2 })).toBe(false);
    expect(isEditorDraft({ ...draft, subject: "" })).toBe(false);
    expect(isEditorDraft({ ...draft, features: [{ id: "invalid" }] })).toBe(false);
    expect(isEditorDraft({ ...draft, visibility: [["feature-1", "false"]] })).toBe(false);
  });

  it("compares server content independently of serialization order and timestamps", () => {
    const first = makeFeature();
    const second = makeFeature("feature-2");
    const server = {
      ...first,
      updatedAt: "2026-11-11T12:00:00Z",
      properties: { mapElementType: "point" as const, name: "Avant" },
    };
    expect(haveSameEditorFeatures([first, second], [second, server])).toBe(true);
    expect(haveSameEditorFeatures([first], [{ ...first, geometry: { type: "Point", coordinates: [20, 10] } }])).toBe(false);
    expect(haveSameEditorFeatures([first, second], [first])).toBe(false);
  });
});

describe("editor draft storage", () => {
  it("snapshots Vue state, omits token fields and only reports success after transaction commit", async () => {
    const database = mockDatabase();
    const file = new File(["image"], "image.png");
    const draft = reactive(makeDraft({ forms: { addImage: { selectedFile: file } } }));
    let saved = false;
    const operation = writeEditorDraft(Object.assign(draft, { token: "not-persisted", refreshToken: "not-persisted" }))
      .then(() => { saved = true; });
    draft.features[0].properties.name = "Modification suivante";
    await flushRequests();

    const written = database.store.put.mock.calls[0][0];
    expect(written.features[0].properties.name).toBe("Avant");
    expect(written.forms.addImage?.selectedFile).toBe(file);
    expect(written).not.toHaveProperty("token");
    expect(written).not.toHaveProperty("refreshToken");
    expect(saved).toBe(false);
    database.complete();
    await operation;
    expect(saved).toBe(true);
  });

  it("rejects a write that is aborted after put instead of allowing a redirect on false success", async () => {
    const database = mockDatabase();
    const operation = writeEditorDraft(makeDraft());
    const rejected = expect(operation).rejects.toThrow("Quota dépassé");
    await flushRequests();
    database.transaction.error = new DOMException("Quota dépassé", "QuotaExceededError");
    database.transaction.abort();
    await rejected;
    expect(database.rows.size).toBe(0);
  });

  it("refuses to overwrite a draft belonging to another identity", async () => {
    const database = mockDatabase([makeDraft({ subject: "other-account" })]);
    const rejected = expect(writeEditorDraft(makeDraft())).rejects.toThrow("autre compte ou projet");
    await rejected;
    expect(database.store.put).not.toHaveBeenCalled();
  });

  it("does not expose or delete a draft outside the requested project/account", async () => {
    const draft = makeDraft();
    const database = mockDatabase([draft]);
    const wrongScope = { projectId: draft.projectId, subject: "other-account" };
    const read = readEditorDraft(draft.id, wrongScope);
    await flushRequests();
    database.complete();
    await expect(read).resolves.toBeNull();

    await expect(deleteEditorDraft(draft.id, wrongScope)).rejects.toThrow("autre compte ou projet");
    expect(database.store.delete).not.toHaveBeenCalled();
    expect(database.rows.get(draft.id)).toBe(draft);
  });

  it("lists only matching account/project drafts, keeping multiple tab drafts and guests separate", async () => {
    const first = makeDraft();
    const newer = makeDraft({ id: "draft-2", updatedAt: 200 });
    const database = mockDatabase([
      first, newer,
      makeDraft({ id: "guest", subject: null }),
      makeDraft({ id: "other-account", subject: "other-account" }),
      makeDraft({ id: "other-project", projectId: "other-project" }),
    ]);
    const drafts = listEditorDrafts(first.projectId, first.subject);
    await flushRequests();
    database.complete();
    await expect(drafts).resolves.toEqual([newer, first]);
  });

  it("keeps an unreadable draft instead of deleting it during recovery", async () => {
    const draft = { ...makeDraft(), version: 2 };
    const database = mockDatabase([draft]);
    await expect(readEditorDraft(draft.id, draft)).rejects.toThrow("version non prise en charge");
    expect(database.rows.get(draft.id)).toBe(draft);
    expect(database.store.delete).not.toHaveBeenCalled();
  });
});
