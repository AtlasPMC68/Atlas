// composables/usePolling.ts
import { getCurrentInstance, onBeforeUnmount, ref } from "vue";

// Runs `tick` every `intervalMs` until stopped. One timer at a time, a tick
// never overlaps the previous one, and the timer dies with the component --
// a poller outliving its page is how a "cancelled" import used to redirect
// the user anyway.
export function usePolling(tick: () => Promise<void> | void, intervalMs: number) {
  const isPolling = ref(false);
  let timer: ReturnType<typeof setTimeout> | null = null;

  const schedule = () => {
    timer = setTimeout(async () => {
      if (!isPolling.value) return;
      try {
        await tick();
      } finally {
        if (isPolling.value) schedule();
      }
    }, intervalMs);
  };

  const start = () => {
    if (isPolling.value) return;
    isPolling.value = true;
    schedule();
  };

  const stop = () => {
    isPolling.value = false;
    if (timer) clearTimeout(timer);
    timer = null;
  };

  if (getCurrentInstance()) onBeforeUnmount(stop);

  return { isPolling, start, stop };
}
