import { defineStore } from "pinia";

export interface ImportData {
  id?: string;
  name?: string;
  timestamp?: string;
  [key: string]: unknown;
}

export const useImportStore = defineStore("import", {
  state: () => ({
    currentImport: null as ImportData | null,
    importHistory: [] as ImportData[],
    isImporting: false,
  }),

  actions: {
    setCurrentImport(importData: ImportData) {
      this.currentImport = importData;
    },

    addToHistory(importData: ImportData) {
      this.importHistory.push({
        ...importData,
        timestamp: new Date().toISOString(),
      });
    },

    resetImport() {
      this.currentImport = null;
      this.isImporting = false;
    },
  },
});
