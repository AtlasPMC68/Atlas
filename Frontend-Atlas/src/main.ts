import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { router } from "./router";
import "./style.css";
import keycloak from "./keycloak";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.config.globalProperties.$keycloak = keycloak;

keycloak
  .init({ onLoad: "check-sso", pkceMethod: "S256" })
  .then((authenticated) => {
    console.log("Keycloak authenticated?", authenticated);
    app.mount("#app");
  })
  .catch(() => {
    app.mount("#app");
  });
