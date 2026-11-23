import demarrageUrl from "../assets/Atlas_Guide_de_demarrage.pdf?url";
import projetUrl from "../assets/Atlas_Guide_Projet.pdf?url";
import importationUrl from "../assets/Atlas_Guide_Importation.pdf?url";

export type GuideId = "demarrage" | "projet" | "importation";

export interface Guide {
  id: GuideId;
  title: string;
  description: string;
  url: string;
}

export const GUIDES: Record<GuideId, Guide> = {
  demarrage: {
    id: "demarrage",
    title: "Guide de démarrage",
    description: "Inscription, connexion, accueil, Mes projets et Explorer.",
    url: demarrageUrl,
  },
  projet: {
    id: "projet",
    title: "Travailler dans un projet",
    description: "L'éditeur de carte bouton par bouton : dessiner, écrire, modifier et enregistrer.",
    url: projetUrl,
  },
  importation: {
    id: "importation",
    title: "Importer une carte",
    description: "Ajouter une carte au projet, de l'image jusqu'à la validation des textes.",
    url: importationUrl,
  },
};

export const GUIDE_LIST: Guide[] = [GUIDES.demarrage, GUIDES.projet, GUIDES.importation];

// Pages of the import guide, so each "i" opens the PDF where its step is explained.
export const IMPORT_GUIDE_PAGES = {
  addMap: 2,
  upload: 3,
  saisie: 4,
  validation: 10,
} as const;

/** URL of a guide, opened at a given page by browsers' built-in PDF viewers. */
export function guideUrl(id: GuideId, page?: number): string {
  const url = GUIDES[id].url;
  return page ? `${url}#page=${page}` : url;
}
