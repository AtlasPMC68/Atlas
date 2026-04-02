<template>
  <Transition
    enter-active-class="transition ease-out duration-300"
    enter-from-class="opacity-0 translate-y-2"
    enter-to-class="opacity-100 translate-y-0"
    leave-active-class="transition ease-in duration-200"
    leave-from-class="opacity-100 translate-y-0"
    leave-to-class="opacity-0 translate-y-2"
  >
    <div
      v-if="alert"
      role="alert"
      :class="[
        'alert fixed bottom-6 right-6 z-[1000] w-auto max-w-sm shadow-lg',
        alert.type === 'success' ? 'alert-success' : 'alert-error',
      ]"
    >
      <span>{{ alert.message }}</span>
      <button class="btn btn-ghost btn-xs" @click="clearAlert">✕</button>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { useAlert } from "../composables/useAlert";

const { alert, clearAlert } = useAlert();
</script>
