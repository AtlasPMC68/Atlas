<script setup lang="ts">
import { onMounted } from "vue";
import { PencilSquareIcon } from "@heroicons/vue/24/solid";
import { useRouter } from "vue-router";
import { useCurrentUser } from "../composables/useCurrentUser";

const router = useRouter();
const goToSettings = () => router.push("/parametres");

const { currentUser, isLoading, fetchCurrentUser } = useCurrentUser();

onMounted(async () => {
  await fetchCurrentUser();
});
</script>

<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
    <div
      class="bg-white shadow rounded-lg p-6 flex flex-col md:flex-row gap-6 items-start"
    >
      <div
        class="w-32 h-32 rounded-full border border-gray-300 bg-gray-100 flex items-center justify-center text-gray-400 text-4xl"
      >
        {{ currentUser.username.charAt(0).toUpperCase() }}
      </div>

      <div class="flex-1">
        <div class="flex justify-between items-start flex-wrap gap-4">
          <div>
            <div class="flex items-center gap-2">
              <h2 class="text-2xl font-bold text-gray-900">
                {{ currentUser.username }}
              </h2>
              <button
                @click="goToSettings"
                class="text-gray-500 hover:text-primary-600 transition"
              >
                <PencilSquareIcon class="h-6 w-6" />
              </button>
            </div>
            <p class="text-sm text-gray-500">{{ currentUser.email }}</p>
          </div>
        </div>

        <p class="mt-4 text-sm text-gray-400">
          Membre depuis le
          {{ new Date(currentUser.createdAt).toLocaleDateString("fr-CA") }}
        </p>
      </div>
    </div>
  </div>
</template>
