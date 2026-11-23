import { onBeforeUnmount, ref, shallowRef } from "vue";
import {
  createEditorDraftId,
  deleteEditorDraft,
  listEditorDrafts,
  readEditorDraft,
  writeEditorDraft,
} from "../services/editorDraft";
import type { EditorDraft } from "../typescript/editorDraft";

type DraftContent = Pick<EditorDraft,
  "features" | "visibility" | "persistedFeatureIds" | "pendingDeletions" |
  "baseFeatures" | "forms" | "savePhase" | "targetProjectId">;
type ResumeMarker = Pick<EditorDraft, "id" | "projectId" | "subject">;
const RESUME_KEY = "atlas.editor.resume.v1";

/** Local persistence is independent of authentication and of server saves. */
export function useEditorDraft(options: {
  subject: () => string | null;
  capture: () => DraftContent;
}) {
  const dirty = ref(false);
  const ready = ref(false);
  const error = ref("");
  const savedAt = ref<number | null>(null);
  const candidates = shallowRef<EditorDraft[]>([]);
  let projectId = "";
  let subject: string | null = null;
  let id = createEditorDraftId();
  let revision = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let writes: Promise<void> = Promise.resolve();
  let restoredFrom: EditorDraft | null = null;

  function cancelTimer() {
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
  }

  async function initialize(nextProjectId: string) {
    cancelTimer();
    ready.value = false;
    await writes.catch(() => {});
    projectId = nextProjectId;
    subject = options.subject();
    id = createEditorDraftId();
    revision = 0;
    dirty.value = false;
    savedAt.value = null;
    restoredFrom = null;
    error.value = "";
    candidates.value = [];
    try {
      candidates.value = await listEditorDrafts(projectId, subject);
    } catch {
      error.value = "Le stockage local est indisponible. Le travail ne pourra pas être protégé avant une reconnexion.";
    }
    ready.value = true;
  }

  function markChanged() {
    if (!ready.value) return;
    revision++;
    dirty.value = true;
    cancelTimer();
    timer = setTimeout(() => { void flush().catch(() => {}); }, 500);
  }

  async function flush(intent: EditorDraft["intent"] = null, force = false): Promise<EditorDraft | null> {
    cancelTimer();
    if (!ready.value || !projectId || (!dirty.value && !force)) return null;
    // Capture now, before awaiting anything. The service clones data at its boundary.
    const draft: EditorDraft = {
      version: 1, id, projectId, subject, updatedAt: Date.now(),
      ...options.capture(), intent,
    };
    const capturedRevision = revision;
    const write = writes.catch(() => {}).then(() => writeEditorDraft(draft));
    writes = write;
    try {
      await write;
      if (id === draft.id && revision === capturedRevision) {
        savedAt.value = draft.updatedAt;
        error.value = "";
      }
      return draft;
    } catch {
      error.value = "Impossible de conserver le brouillon sur cet appareil. Gardez cette page ouverte et libérez de l’espace ou autorisez le stockage du site.";
      throw new Error(error.value);
    }
  }

  async function prepareRedirect(intent: "resume" | "save") {
    const draft = await flush(intent, true);
    if (!draft) throw new Error("L’éditeur n’est pas encore prêt pour la reconnexion.");
    try {
      const marker: ResumeMarker = { id: draft.id, projectId, subject };
      sessionStorage.setItem(RESUME_KEY, JSON.stringify(marker));
    } catch {
      error.value = "Le navigateur ne permet pas de préparer le retour à la carte. La page reste ouverte pour conserver votre travail.";
      throw new Error(error.value);
    }
  }

  async function takeResume(): Promise<EditorDraft | null> {
    try {
      const raw = sessionStorage.getItem(RESUME_KEY);
      if (!raw) return null;
      const marker = JSON.parse(raw) as ResumeMarker;
      if (marker.projectId !== projectId || typeof marker.id !== "string") return null;
      // A guest draft can be claimed only through this tab's explicit login return.
      if (marker.subject !== null && marker.subject !== options.subject()) {
        error.value = "Un brouillon attend la reconnexion avec le compte utilisé avant l’interruption. Aucun changement n’a été envoyé.";
        return null;
      }
      if (!options.subject()) return null;
      const draft = await readEditorDraft(marker.id, {
        projectId: marker.projectId, subject: marker.subject,
      });
      // Consume before resuming a save, preventing a redirect/save loop on reload.
      sessionStorage.removeItem(RESUME_KEY);
      return draft;
    } catch {
      error.value = "Impossible de récupérer le brouillon de reconnexion. Il n’a pas été supprimé.";
      return null;
    }
  }

  async function adopt(draft: EditorDraft) {
    if (draft.projectId !== projectId ||
      (draft.subject !== null && draft.subject !== options.subject())) {
      throw new Error("Ce brouillon appartient à un autre compte ou projet.");
    }
    // Fork the restored draft: another open editor must not overwrite this one.
    restoredFrom = draft;
    id = createEditorDraftId();
    subject = options.subject();
    candidates.value = [];
    dirty.value = true;
    revision++;
    await flush(null, true);
  }

  async function removeRestoredSource() {
    if (!restoredFrom) return;
    const source = restoredFrom;
    const scope = { projectId: source.projectId, subject: source.subject };
    const current = await readEditorDraft(source.id, scope);
    // Do not remove a newer draft written by the original tab.
    if (current?.updatedAt === source.updatedAt) await deleteEditorDraft(source.id, scope);
    restoredFrom = null;
  }

  async function complete(hasOpenForms: boolean) {
    cancelTimer();
    await writes.catch(() => {});
    if (hasOpenForms) {
      dirty.value = true;
      await flush(null, true);
    } else {
      await deleteEditorDraft(id, { projectId, subject });
      dirty.value = false;
      savedAt.value = null;
    }
    await removeRestoredSource();
  }

  async function discardCandidate(draft: EditorDraft) {
    await deleteEditorDraft(draft.id, { projectId, subject: options.subject() });
    candidates.value = candidates.value.filter((item) => item.id !== draft.id);
  }

  onBeforeUnmount(cancelTimer);
  return { dirty, ready, error, savedAt, candidates, initialize, markChanged,
    flush, prepareRedirect, takeResume, adopt, complete, discardCandidate };
}
