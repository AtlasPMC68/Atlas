<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { useCurrentUser } from "../composables/useCurrentUser";
import keycloak from "../keycloak";

const router = useRouter();
const goToTestBrowser = () => router.push("/tests");

const { currentUser, fetchCurrentUser } = useCurrentUser();

onMounted(async () => {
  await fetchCurrentUser();
});

const logout = async () => {
  await keycloak.logout();
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
        <button class="btn btn-secondary" @click="goToTestBrowser">
          Voir les tests
        </button>

        <button class="btn btn-error text-white" @click="logout">
          Déconnexion
        </button>
      </div>
    </div>
  </div>
</template>
