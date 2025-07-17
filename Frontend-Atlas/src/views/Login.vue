<template>
  <div class="min-h-screen bg-gradient-to-br from-primary-50 to-secondary-50 flex items-center justify-center px-6">
    <div class="max-w-md w-full">
      <!-- Logo -->
      <div class="text-center mb-8">
        <router-link to="/" class="inline-flex items-center space-x-2">
          <MapIcon class="h-10 w-10 text-primary-600" />
          <span class="text-2xl font-bold text-gray-900">Atlas</span>
        </router-link>
      </div>

      <!-- Login Form -->
      <div class="card p-8">
        <div class="text-center mb-6">
          <h2 class="text-2xl font-bold text-gray-900 mb-2">Connexion</h2>
        </div>

        <form @submit.prevent="handleLogin" class="space-y-6">
          <div class="flex flex-col gap-4 items-center justify-center">
            <div class="w-full max-w-sm">
              <label for="email" class="block text-sm font-medium text-gray-700 mb-2">
                Adresse email
              </label>
              <input
                id="email"
                v-model="email"
                type="email"
                required
                class="input-field py-3 px-4 text-base w-full"
                placeholder="votre@email.com"
              >
            </div>

            <div class="w-full max-w-sm">
              <label for="password" class="block text-sm font-medium text-gray-700 mb-2">
                Mot de passe
              </label>
              <input
                id="password"
                v-model="password"
                type="password"
                required
                class="input-field py-3 px-4 text-base w-full"
                placeholder="Votre mot de passe"
              >
            </div>
          </div>

          <div class="flex items-center justify-between">
            <label class="flex items-center">
              <input type="checkbox" class="rounded border-gray-300 text-primary-600 focus:ring-primary-500">
              <span class="ml-2 text-sm text-gray-600">Se souvenir de moi</span>
            </label>
          </div>

          <div class="w-full max-w-sm mx-auto">
            <button type="submit" class="btn-primary w-full py-3 text-base" :disabled="loading">
                <span v-if="loading" class="flex items-center justify-center">
                <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Connexion...
                </span>
                <span v-else>Se connecter</span>
            </button>
          </div>

          <div v-if="error" class="text-red-600 text-sm text-center">
            {{ error }}
          </div>
        </form>

        <div class="mt-6 text-center">
          <p class="text-gray-600">
            Pas encore de compte ?
            <router-link to="/inscription" class="text-primary-600 hover:text-primary-700 font-medium">
              Créer un compte
            </router-link>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { MapIcon } from '@heroicons/vue/24/outline'

const router = useRouter()
const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  error.value = ''
  loading.value = true

  try {
    const response = await fetch('http://localhost:8000/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email: email.value,
        password: password.value,
      }),
    })

    if (!response.ok) {
      const result = await response.json()
      throw new Error(result.detail || "Échec de la connexion.")
    }

    const data = await response.json()
    console.log('Connexion réussie:', data)

    localStorage.setItem('access_token', data.access_token)

    const token = localStorage.getItem('access_token')

    const meRes = await fetch('http://localhost:8000/me', {
      headers: {
        Authorization: `Bearer ${token}`
      }
    })

    if (!meRes.ok) {
      throw new Error("Le token est invalide ou expiré.")
    }

    router.push('/tableau-de-bord')

  } catch (err: any) {
    error.value = err.message
    console.error(err)
  } finally {
    loading.value = false
  }
}
</script>