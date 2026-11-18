import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { router } from "./router";
import "./style.css";
import keycloak from "./keycloak";
import { startTokenRefresh } from "./services/tokenRefresh";
import { initializeAuthSession, reportInitializationFailure, syncAuthenticatedSession } from "./services/authSession";
import "leaflet/dist/leaflet.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.config.globalProperties.$keycloak = keycloak;

initializeAuthSession();
keycloak
  .init({
    onLoad: "check-sso",
    pkceMethod: "S256",
    checkLoginIframe: true,
  })
  .then(() => {
    syncAuthenticatedSession();
    const stopTokenRefresh = startTokenRefresh();
    import.meta.hot?.dispose(stopTokenRefresh);
    app.mount("#app");
  })
  .catch(() => {
    reportInitializationFailure();
    app.mount("#app");
  });
