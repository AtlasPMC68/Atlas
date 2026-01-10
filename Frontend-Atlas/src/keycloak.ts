import Keycloak from "keycloak-js";

// Extend Keycloak interface to include our custom methods
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

// Add initialization flag
(keycloak as any).didInitialize = false;

// Override init to set the flag
const originalInit = keycloak.init.bind(keycloak);
keycloak.init = function (options: any) {
  return originalInit(options).then((result: any) => {
    (keycloak as any).didInitialize = true;
    return result;
  });
};

// Add login method that redirects to Keycloak realm 'atlas'
(keycloak as any).loginToAtlas = function (options?: any) {
  return this.login({
    redirectUri: options?.redirectUri || window.location.origin,
    ...options,
  });
};

export default keycloak;
