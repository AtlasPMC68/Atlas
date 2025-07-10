<script setup lang="ts">
import { ref } from 'vue'

const name = ref('Alexis Guerard')
const email = ref('alexis@example.com')
const language = ref('fr')
const notificationsEnabled = ref(true)

const saveSettings = () => {
  console.log('Saving settings:', {
    name: name.value,
    email: email.value,
    language: language.value,
    notifications: notificationsEnabled.value,
  })
}
</script>

<template>
  <div class="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
    <h1 class="text-2xl font-bold text-gray-900 mb-6">Paramètres</h1>

    <div class="bg-white shadow rounded-lg p-6 space-y-6">

      <!-- Nom -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Nom complet</label>
        <input
          type="text"
          v-model="name"
          class="w-full border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
      </div>

      <!-- Courriel -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Adresse courriel</label>
        <input
          type="email"
          v-model="email"
          class="w-full border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
      </div>

      <!-- Langue -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Langue préférée</label>
        <select
          v-model="language"
          class="w-full border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="fr">Français</option>
          <option value="en">Anglais</option>
        </select>
      </div>

      <!-- Bouton enregistrer -->
      <div class="pt-4">
        <button @click="saveSettings" class="btn-primary">
          Enregistrer les modifications
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.btn-primary {
  @apply bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition;
}
</style>
