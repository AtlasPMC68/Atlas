import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { router } from "./router";
import "./style.css";

const app = createApp(App);

// Créer et configurer Pinia
const pinia = createPinia();
app.use(pinia);

app.use(router);
app.mount("#app");
