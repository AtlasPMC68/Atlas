<template>
  <dialog ref="dialogRef" class="modal" @close="onClose">
    <div class="modal-box max-w-md relative">
      <button
        type="button"
        class="btn btn-sm btn-circle btn-ghost absolute right-4 top-4 z-10"
        @click="close('cancel')"
      >
        ✕
      </button>
      <h3 class="font-bold text-xl">{{ title }}</h3>
      <p class="py-3 text-sm text-base-content/70">{{ message }}</p>
      <div class="modal-action mt-6 flex justify-end gap-2">
        <button type="button" class="modal-secondary-btn w-32" @click="close('cancel')">
          {{ cancelLabel }}
        </button>
        <button
          type="button"
          class="btn rounded-lg w-32"
          :class="danger ? 'btn-error text-white' : 'btn-warning text-white'"
          @click="close('confirm')"
        >
          {{ confirmLabel }}
        </button>
      </div>
    </div>
  </dialog>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";

withDefaults(
  defineProps<{
    title: string;
    message: string;
    confirmLabel?: string;
    cancelLabel?: string;
    // Irreversible: the confirm button is red rather than amber.
    danger?: boolean;
  }>(),
  { confirmLabel: "Continuer", cancelLabel: "Annuler", danger: false },
);

const emit = defineEmits<{
  (e: "confirm"): void;
  (e: "cancel"): void;
}>();

const dialogRef = ref<HTMLDialogElement | null>(null);

// Mounted open: the parent shows it with v-if.
onMounted(() => dialogRef.value?.showModal());

function close(reason: "confirm" | "cancel") {
  dialogRef.value?.close(reason);
}

// ESC closes with an empty return value, which counts as a cancel.
function onClose() {
  if (dialogRef.value?.returnValue === "confirm") emit("confirm");
  else emit("cancel");
}
</script>
