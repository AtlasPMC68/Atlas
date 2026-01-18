import Keycloak from "keycloak-js";

declare module "keycloak-js" {
  interface Keycloak {
    didInitialize: boolean;
    loginToAtlas(options?: any): Promise<void>;
  }
}

const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL,
  realm: import.meta.env.VITE_KEYCLOAK_REALM,
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID,
});

(keycloak as any).didInitialize = false;

const originalInit = keycloak.init.bind(keycloak);
keycloak.init = function (options: any) {
  return originalInit(options)
    .then((result: any) => {
      (keycloak as any).didInitialize = true;
      return result;
    })
    .catch((error: any) => {
      (keycloak as any).didInitialize = true;
      throw error;
    });
};

(keycloak as any).loginToAtlas = function (options?: any) {
  return this.login({
    redirectUri: options?.redirectUri || window.location.origin,
    ...options,
  });
};

export default keycloak;
