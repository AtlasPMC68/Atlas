import { defineStore } from 'pinia'

export const useImportStore = defineStore('import', {
  state: () => ({
    currentImport: null,
    importHistory: [],
    isImporting: false
  }),

  actions: {
    setCurrentImport(importData) {
      this.currentImport = importData
    },

    addToHistory(importData) {
      this.importHistory.push({
        ...importData,
        timestamp: new Date().toISOString()
      })
    },

    resetImport() {
      this.currentImport = null
      this.isImporting = false
    }
  }
})