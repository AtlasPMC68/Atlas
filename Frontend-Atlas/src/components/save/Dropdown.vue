<template>
  <div class="relative inline-block text-left">
    <button
      @click="toggleMenu"
      type="button"
      class="inline-flex justify-center w-full p-2 text-sm font-medium text-gray-700 hover:text-gray-900 focus:outline-none"
    >
      <Bars3Icon class="w-6 h-6" />
    </button>

    <div
      v-if="isOpen"
      class="absolute left-0 z-10 mt-2 w-44 origin-top-left rounded-md bg-white shadow-lg ring-1 ring-black ring-opacity-5"
    >
      <div class="py-1">
        <button
          @click="onSave"
          class="flex items-center w-full gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100"
        >
          <ArrowDownTrayIcon class="w-5 h-5" />
          Enregistrer
        </button>
        <button
          @click="onSaveAs"
          class="flex items-center w-full gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100"
        >
          <ArchiveBoxArrowDownIcon class="w-5 h-5" />
          Enregistrer Sous...
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { Bars3Icon, ArrowDownTrayIcon, ArchiveBoxArrowDownIcon } from '@heroicons/vue/24/outline'

const isOpen = ref(false);

function toggleMenu() {
  isOpen.value = !isOpen.value;
}

// Emited event toward the parent
const emit = defineEmits(["save", "save-as"]);

function onSave() {
  emit("save");
  isOpen.value = false;
}

function onSaveAs() {
  emit("save-as");
  isOpen.value = false;
}
</script>

<style scoped>
/* Close the menu if you click outside */
</style>
