<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { useCurrentUser } from "../composables/useCurrentUser";
import keycloak from "../keycloak";
import { DEV_TOOLS_ENABLED } from "../utils/devTools";
import { DocumentTextIcon } from "@heroicons/vue/24/outline";
import { GUIDE_LIST } from "../utils/guides";

const router = useRouter();
const showTests = DEV_TOOLS_ENABLED;
const goToTestBrowser = () => router.push("/tests");

const { currentUser, isLoading, error, fetchCurrentUser } = useCurrentUser();

onMounted(async () => {
  await fetchCurrentUser();
});

const logout = async () => {
  await keycloak.logout({
    redirectUri: window.location.origin,
  });
};
</script>

<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
    <div class="mb-6">
      <h1 class="text-3xl font-semibold tracking-tight text-gray-900">
        Profil
      </h1>
      <p class="mt-1 text-gray-500">
        Consultez les informations de votre compte.
      </p>
    </div>

    <div
      v-if="currentUser"
      class="bg-white shadow-sm border border-gray-200 rounded-xl overflow-hidden"
    >
      <div class="p-6">
        <div class="flex items-center gap-4 pb-6 border-b border-gray-200">
          <div
            class="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-semibold text-lg"
          >
            {{ currentUser!.username.charAt(0).toUpperCase() }}
          </div>

          <div>
            <h2 class="text-xl font-semibold text-gray-900">
              {{ currentUser!.username }}
            </h2>
            <p class="text-sm text-gray-500">
              {{ currentUser!.email }}
            </p>
          </div>
        </div>

        <div class="py-6 flex flex-col gap-5">
          <div>
            <p class="text-sm font-medium text-gray-500">Nom d'utilisateur</p>
            <p class="mt-1 text-gray-900">
              {{ currentUser!.username }}
            </p>
          </div>

          <div>
            <p class="text-sm font-medium text-gray-500">Adresse courriel</p>
            <p class="mt-1 text-gray-900">
              {{ currentUser!.email }}
            </p>
          </div>

          <div>
            <p class="text-sm font-medium text-gray-500">Membre depuis</p>
            <p class="mt-1 text-gray-900">
              {{ new Date(currentUser!.createdAt).toLocaleDateString("fr-CA") }}
            </p>
          </div>
        </div>
      </div>

      <div
        class="px-6 py-4 bg-gray-50 border-t border-gray-200 flex flex-col sm:flex-row justify-between gap-3"
      >
        <button v-if="showTests" class="btn btn-secondary" @click="goToTestBrowser">
          Voir les tests
        </button>

        <button class="btn btn-error text-white sm:ml-auto" @click="logout">
          Déconnexion
        </button>
      </div>
    </div>
    <div v-else-if="isLoading" class="text-gray-500">Chargement du profil...</div>
    <div v-else-if="error" class="flex flex-col items-start gap-3 text-gray-600">
      <p>Impossible de charger le profil. Vérifiez que le serveur est disponible.</p>
      <button
        type="button"
        class="btn btn-sm btn-outline text-gray-700"
        @click="fetchCurrentUser"
      >
        Réessayer
      </button>
    </div>

    <section
      class="mt-8 bg-white shadow-sm border border-gray-200 rounded-xl overflow-hidden"
      data-testid="profile-guides"
    >
      <div class="px-6 pt-6 pb-2">
        <h2 class="text-xl font-semibold text-gray-900">Guides d'utilisation</h2>
        <p class="mt-1 text-sm text-gray-500">
          Consultez ou téléchargez les guides d'Atlas en format PDF.
        </p>
      </div>
      <ul class="divide-y divide-gray-200">
        <li
          v-for="guide in GUIDE_LIST"
          :key="guide.id"
          class="px-6 py-4 flex items-center gap-4"
        >
          <div
            class="w-10 h-10 shrink-0 rounded-lg bg-blue-50 flex items-center justify-center text-blue-600"
          >
            <DocumentTextIcon class="w-6 h-6" />
          </div>
          <div class="flex-1 min-w-0">
            <p class="font-medium text-gray-900">{{ guide.title }}</p>
            <p class="text-sm text-gray-500">{{ guide.description }}</p>
          </div>
          <a
            :href="guide.url"
            target="_blank"
            rel="noopener"
            class="btn btn-sm btn-outline btn-primary shrink-0"
          >
            Ouvrir
          </a>
        </li>
      </ul>
    </section>
  </div>
</template>
