<script setup lang="ts">
import { ref } from 'vue'
import { PencilSquareIcon, KeyIcon } from '@heroicons/vue/24/outline'

const user = ref({
  name: 'Alexis Guerard',
  email: 'alexis@exemple.com',
  bio: 'Étudiant en génie informatique',
  createdAt: '2023-11-15',
})
</script>

<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
    <div class="bg-white shadow rounded-lg p-6 flex flex-col md:flex-row gap-6 items-start">
      
      <!-- Avatar Placeholder -->
      <div class="w-32 h-32 rounded-full border border-gray-300 bg-gray-100 flex items-center justify-center text-gray-400 text-xl">
        <!--TODO: Placeholder icon or initials later -->
        ?
      </div>

      <!-- Profile Info -->
      <div class="flex-1">
        <div class="flex justify-between items-start flex-wrap gap-4">
          <div>
            <h2 class="text-2xl font-bold text-gray-900">{{ user.name }}</h2>
            <p class="text-sm text-gray-500">{{ user.email }}</p>
          </div>

          <div class="flex gap-2">
            <button
              class="btn-secondary flex items-center gap-2 text-sm"
              @click="console.log('Change password')"
            >
              <KeyIcon class="h-5 w-5" />
              Changer le mot de passe
            </button>
            <button
              class="btn-primary flex items-center gap-2 text-sm"
              @click="console.log('Edit profile')"
            >
              <PencilSquareIcon class="h-5 w-5" />
              Editer le profil
            </button>
          </div>
        </div>

        <p class="mt-4 text-gray-700 whitespace-pre-line">{{ user.bio }}</p>

        <p class="mt-4 text-sm text-gray-400">
          Membre depuis le {{ new Date(user.createdAt).toLocaleDateString('en-CA') }}
        </p>
      </div>
    </div>

    <!-- Section for projects, etc. -->
    <div class="mt-10">
      <h3 class="text-xl font-semibold text-gray-800 mb-4">Mes Projets</h3>
      <p class="text-sm text-gray-500">Aucun projet</p>
    </div>
  </div>
</template>

<style scoped>
.btn-primary {
  @apply bg-primary-600 text-white px-3 py-2 rounded-lg hover:bg-primary-700 transition;
}
.btn-secondary {
  @apply border border-gray-300 text-gray-700 px-3 py-2 rounded-lg hover:bg-gray-100 transition;
}
</style>
