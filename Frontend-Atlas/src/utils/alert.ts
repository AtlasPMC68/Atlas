import type { Ref } from "vue";
import type { AlertState, AlertType } from "../typescript/alert";

const timeoutMap = new WeakMap<object, ReturnType<typeof setTimeout>>();

export function showAlert(
  alert: Ref<AlertState>,
  type: AlertType,
  message: string,
) {
  alert.value = { type, message };

  const existingTimeout = timeoutMap.get(alert);
  if (existingTimeout) {
    clearTimeout(existingTimeout);
  }

  const timeoutId = setTimeout(() => {
    alert.value = null;
    timeoutMap.delete(alert);
  }, 4000);

  timeoutMap.set(alert, timeoutId);
}

export function clearAlert(alert: Ref<AlertState>) {
  const existingTimeout = timeoutMap.get(alert);
  if (existingTimeout) {
    clearTimeout(existingTimeout);
    timeoutMap.delete(alert);
  }

  alert.value = null;
}