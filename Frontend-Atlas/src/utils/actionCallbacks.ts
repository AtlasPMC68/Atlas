import { showAlert } from "../composables/useAlert";
import type { Ref } from "vue";

export interface ActionCallbackOptions {
  successMessage?: string | (() => string);
  errorFallback?: string;
  loadingRef?: Ref<boolean>;
  dialogRef?: Ref<{ close: () => void } | HTMLDialogElement | null | undefined>;
  onSuccess?: () => void;
  onError?: (err?: string) => void;
}

export function createActionCallbacks(options: ActionCallbackOptions = {}) {
  return {
    onSuccess: () => {
      if (options.successMessage) {
        const msg =
          typeof options.successMessage === "function"
            ? options.successMessage()
            : options.successMessage;
        showAlert("success", msg);
      }
      if (options.loadingRef) options.loadingRef.value = false;
      if (options.dialogRef?.value) {
        options.dialogRef.value.close();
      }
      options.onSuccess?.();
    },
    onError: (message?: string) => {
      showAlert(
        "error",
        message || options.errorFallback || "Une erreur est survenue.",
      );
      if (options.loadingRef) options.loadingRef.value = false;
      options.onError?.(message);
    },
  };
}
