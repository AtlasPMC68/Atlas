import { ref } from "vue";

const alert = ref<{ type: "success" | "error"; message: string } | null>(null);
let timer: ReturnType<typeof setTimeout> | null = null;

export function showAlert(
  type: "success" | "error",
  message: string,
  duration = 4000,
) {
  alert.value = { type, message };
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => {
    alert.value = null;
    timer = null;
  }, duration);
}

export function clearAlert() {
  if (timer) clearTimeout(timer);
  timer = null;
  alert.value = null;
}

export function useAlert() {
  return { alert, clearAlert };
}
