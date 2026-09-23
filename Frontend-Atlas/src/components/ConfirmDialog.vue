<template>
  <dialog ref="dialogRef" class="modal" @close="onClose">
    <div class="modal-box max-w-md">
      <h3 class="font-bold text-lg">{{ title }}</h3>
      <p class="py-3 text-sm text-base-content/70">{{ message }}</p>
      <div class="modal-action">
        <button type="button" class="btn btn-ghost btn-sm" @click="close('cancel')">
          {{ cancelLabel }}
        </button>
        <button type="button" class="btn btn-warning btn-sm" @click="close('confirm')">
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
  }>(),
  { confirmLabel: "Continuer", cancelLabel: "Annuler" },
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
