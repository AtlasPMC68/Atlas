import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { router } from "./router";
import "./style.css";
import keycloak from "./keycloak";
import "leaflet/dist/leaflet.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.config.globalProperties.$keycloak = keycloak;

keycloak
  .init({
    onLoad: "check-sso",
    pkceMethod: "S256",
    checkLoginIframe: true,
  })
  .then(() => {
    app.mount("#app");
  })
  .catch(() => {
    app.mount("#app");
  });
