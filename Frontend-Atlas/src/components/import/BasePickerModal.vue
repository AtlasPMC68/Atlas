<template>
  <dialog ref="modalRef" class="modal" @close="onDialogClose">
    <div class="modal-box max-w-5xl w-full flex flex-col gap-4">
      <form method="dialog">
        <button
          value="cancel"
          class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2"
        >
          ✕
        </button>
      </form>

      <h2 class="text-xl font-semibold">{{ title }}</h2>

      <p class="text-sm text-base-content/70">
        {{ description }}
      </p>

      <div class="border rounded-md overflow-hidden flex flex-col">
        <slot name="image-area"></slot>
      </div>

      <slot name="list-area"></slot>

      <slot name="error-area"></slot>

      <div class="modal-action">
        <button class="btn btn-ghost" type="button" @click="requestClose">
          Annuler
        </button>
        <button
          v-if="showSkip"
          class="btn btn-outline"
          type="button"
          @click="onSkip"
        >
          Sauter l'étape
        </button>
        <button
          class="btn btn-primary"
          type="button"
          :disabled="isConfirmDisabled"
          @click="onConfirm"
        >
          {{ confirmLabel }}
        </button>
      </div>
    </div>
  </dialog>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from "vue";
import type { DialogCloseReason } from "../../typescript/colorPicker";

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    title: string;
    description: string;
    confirmLabel: string;
    isConfirmDisabled?: boolean;
    showSkip?: boolean;
  }>(),
  {
    isOpen: false,
    isConfirmDisabled: false,
    showSkip: false,
  },
);

const emit = defineEmits<{
  (e: "close"): void;
  (e: "skip"): void;
  (e: "confirm"): void;
  (e: "opened"): void;
}>();

const modalRef = ref<HTMLDialogElement | null>(null);

let closeReason: DialogCloseReason = "programmatic";

onMounted(() => {
  if (props.isOpen && modalRef.value && !modalRef.value.open) {
    modalRef.value.showModal();
    emit("opened");
  }
});

watch(
  () => props.isOpen,
  (opened) => {
    if (opened) {
      if (modalRef.value && !modalRef.value.open) {
        modalRef.value.showModal();
        emit("opened");
      }
      return;
    }
    if (modalRef.value?.open) {
      closeReason = "programmatic";
      modalRef.value.close();
    }
  },
);

function onDialogClose() {
  const returnValue = modalRef.value?.returnValue;
  const isProgrammaticClose = returnValue === "programmatic";
  const isSuccessClose = closeReason === "success" || returnValue === "success";

  if (!isProgrammaticClose && !isSuccessClose) {
    emit("close");
  }

  closeReason = "programmatic";
}

function requestClose() {
  closeReason = "cancel";
  if (modalRef.value?.open) modalRef.value.close("cancel");
}

function onSkip() {
  closeReason = "success";
  emit("skip");
  if (modalRef.value?.open) modalRef.value.close("success");
}

function onConfirm() {
  if (props.isConfirmDisabled) return;
  closeReason = "success";
  emit("confirm");
  if (modalRef.value?.open) modalRef.value.close("success");
}
</script>
