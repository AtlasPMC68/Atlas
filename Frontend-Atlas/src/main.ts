import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { router } from "./router";
import "./style.css";
import keycloak from "./keycloak";

const app = createApp(App);

const pinia = createPinia();
app.use(pinia);
app.use(router);

app.config.globalProperties.$keycloak = keycloak;

app.mount("#app");

keycloak
  .init({ onLoad: "check-sso", pkceMethod: "S256" })
  .then((authenticated) => {
    console.log("Keycloak authenticated?", authenticated);
  })
  .catch((err) => console.error("Erreur Keycloak :", err));
