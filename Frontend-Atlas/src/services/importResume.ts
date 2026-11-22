import type { ImportInputsPatch } from "../typescript/importSession";
import type { TextValidationEntry } from "../utils/textValidation";

// Work on an import that only this tab holds when it leaves for the login page.
// Confirmed steps live on the backend (map_imports) and come back on their own;
// what is kept here is what never reached it: a step confirmed while the session
// was lost, and the text validation being reviewed. sessionStorage keeps it in
// this tab only and drops it with the tab.
export interface ImportResume {
  version: 1;
  mapId: string;
  projectId: string | null;
  // The account that did the work: another account never receives it.
  subject: string | null;
  inputs: ImportInputsPatch | null;
  validation: TextValidationEntry[] | null;
}

export const IMPORT_RESUME_KEY = "atlas.import.resume.v1";

/** Throws when the browser refuses to store it, so the redirect is not taken. */
export function writeImportResume(resume: Omit<ImportResume, "version">): void {
  try {
    sessionStorage.setItem(IMPORT_RESUME_KEY, JSON.stringify({ version: 1, ...resume }));
  } catch {
    throw new Error(
      "Le navigateur ne permet pas de conserver l'importation avant la reconnexion. La page reste ouverte pour conserver votre travail.",
    );
  }
}

function isImportResume(value: unknown): value is ImportResume {
  const resume = value as ImportResume | null;
  return !!resume && resume.version === 1 && typeof resume.mapId === "string" &&
    (resume.subject === null || typeof resume.subject === "string") &&
    (resume.validation === null || Array.isArray(resume.validation));
}

export type ImportResumeResult =
  | { kind: "none" }
  | { kind: "other-account" }
  | { kind: "resume"; resume: ImportResume };

/**
 * The work kept for this map, removed from storage so it is resumed once only.
 * It is left in place while no one, or another account, is signed in.
 */
export function takeImportResume(mapId: string, subject: string | null): ImportResumeResult {
  let resume: unknown;
  try {
    const raw = sessionStorage.getItem(IMPORT_RESUME_KEY);
    if (!raw) return { kind: "none" };
    resume = JSON.parse(raw);
  } catch {
    return { kind: "none" };
  }
  if (!isImportResume(resume) || resume.mapId !== mapId) return { kind: "none" };
  if (!subject) return { kind: "none" };
  if (resume.subject !== subject) return { kind: "other-account" };
  sessionStorage.removeItem(IMPORT_RESUME_KEY);
  return { kind: "resume", resume };
}
