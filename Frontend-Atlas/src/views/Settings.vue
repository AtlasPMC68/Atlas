<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const username = ref('')
const email = ref('')
const token = localStorage.getItem('access_token')
const errorMessage = ref('')
const router = useRouter()

onMounted(async () => {
  if (!token) return
  try {
    const res = await fetch('http://localhost:8000/me', {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })
    if (!res.ok) throw new Error('Erreur chargement du profil')
    const data = await res.json()
    username.value = data.username
    email.value = data.email
  } catch (err) {
    console.error(err)
  }
})

const saveSettings = async () => {
errorMessage.value = ''

  try {
    const res = await fetch('http://localhost:8000/user/update-user', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ username: username.value }),
    })

    const data = await res.json()

    if (!res.ok) {
      errorMessage.value = data.detail || 'Erreur lors de la mise à jour'
      return
    }
    router.push('/profil')
  } catch (err) {
    console.error(err)
    errorMessage.value = 'Erreur lors de la communication avec le serveur.'
  }
}
</script>

<template>
  <div class="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
    <h1 class="text-2xl font-bold text-gray-900 mb-6">Paramètres</h1>

    <div class="bg-white shadow rounded-lg p-6 space-y-6">
      
      <!-- Username -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Nom d’utilisateur</label>
        <input
          type="text"
          v-model="username"
          class="w-full border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
      </div>

      <!-- Email (readonly) -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Adresse courriel</label>
        <input
          type="email"
          :value="email"
          disabled
          class="w-full border border-gray-300 rounded-lg px-4 py-2 bg-gray-100 text-gray-500"
        />
      </div>

      <!-- Save -->
      <div class="pt-4">
        <button @click="saveSettings" class="btn-primary">
          Enregistrer les modifications
        </button>
      </div>
      <p v-if="errorMessage" class="text-sm text-red-600 mt-2">
        {{ errorMessage }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.btn-primary {
  @apply bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition;
}
</style>
