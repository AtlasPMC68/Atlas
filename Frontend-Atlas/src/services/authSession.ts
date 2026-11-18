import { reactive, readonly } from "vue";
import keycloak from "../keycloak";

export type AuthStatus = "guest" | "authenticated" | "unavailable" | "reauth-required";
export type AuthRedirectIntent = "resume" | "save";

const state = reactive({
  status: "guest" as AuthStatus,
  // Keep the last identity when the SDK clears its tokens so a draft cannot
  // silently change owners when authentication is lost.
  subject: null as string | null,
  message: "",
  redirectError: null as string | null,
});

export const sessionState = readonly(state);
let initializationFailed = false;

export class AuthRequiredError extends Error {
  constructor(message = "Votre session n'est plus disponible. Veuillez vous reconnecter.") {
    super(message);
    this.name = "AuthRequiredError";
  }
}

export function isAuthRequiredError(error: unknown): error is AuthRequiredError {
  return error instanceof Error && error.name === "AuthRequiredError";
}

export function syncAuthenticatedSession(): void {
  initializationFailed = false;
  if (keycloak.authenticated && keycloak.token) {
    state.subject = keycloak.subject ?? keycloak.tokenParsed?.sub ?? state.subject;
    state.status = "authenticated";
    state.message = "";
  } else if (state.subject || state.status === "authenticated" || state.status === "reauth-required") {
    requireReauthentication();
  } else {
    state.status = "guest";
    state.message = "";
  }
}

export function requireReauthentication(): void {
  state.subject = keycloak.subject ?? keycloak.tokenParsed?.sub ?? state.subject;
  state.status = "reauth-required";
  state.message = "Votre session a pris fin ou n'est plus acceptée. Reconnectez-vous pour sauvegarder vos modifications.";
}

export function reportRefreshFailure(): void {
  if (!keycloak.authenticated || !keycloak.token) {
    requireReauthentication();
    return;
  }
  state.subject = keycloak.subject ?? keycloak.tokenParsed?.sub ?? state.subject;
  state.status = "unavailable";
  state.message = "Impossible de vérifier votre session pour le moment. Vérifiez votre connexion, puis réessayez.";
}

export function reportInitializationFailure(): void {
  initializationFailed = true;
  state.status = "unavailable";
  state.message = "Le service de connexion est indisponible. Vous pouvez réessayer sans quitter votre travail.";
}

/** Register before init: Keycloak can report logout outside a refresh attempt. */
export function initializeAuthSession(): void {
  keycloak.onAuthSuccess = syncAuthenticatedSession;
  keycloak.onAuthRefreshSuccess = syncAuthenticatedSession;
  keycloak.onAuthRefreshError = reportRefreshFailure;
  keycloak.onAuthLogout = () => {
    if (state.subject || state.status !== "guest") requireReauthentication();
    else syncAuthenticatedSession();
  };
  // Access-token expiry alone is not proof that the SSO session has ended.
  // Activity and API calls continue to own renewal, including the idle limit.
}

let redirectHandler: ((intent: AuthRedirectIntent) => Promise<string | undefined>) | undefined;

export function registerAuthRedirectHandler(
  handler: (intent: AuthRedirectIntent) => Promise<string | undefined>,
): () => void {
  redirectHandler = handler;
  return () => {
    if (redirectHandler === handler) redirectHandler = undefined;
  };
}

async function redirectAfterPreservingWork(
  action: (redirectUri: string) => Promise<void>,
  intent: AuthRedirectIntent,
  redirectUri?: string,
): Promise<void> {
  state.redirectError = null;
  try {
    const editorUrl = await redirectHandler?.(intent);
    await action(editorUrl ?? redirectUri ?? window.location.href);
  } catch (error) {
    state.redirectError = error instanceof Error
      ? error.message
      : "Impossible de préparer la reconnexion. Vos modifications restent dans cette page.";
    throw error;
  }
}

export function reconnect(
  { intent = "resume", redirectUri }: { intent?: AuthRedirectIntent; redirectUri?: string } = {},
): Promise<void> {
  return redirectAfterPreservingWork((url) => keycloak.login({ redirectUri: url }), intent, redirectUri);
}

export function registerAccount(): Promise<void> {
  return redirectAfterPreservingWork((url) => keycloak.register({ redirectUri: url }), "resume");
}

export function logoutFromAtlas(): Promise<void> {
  return redirectAfterPreservingWork((url) => keycloak.logout({ redirectUri: url }), "resume", window.location.origin);
}

export async function retryAuthentication(): Promise<void> {
  state.redirectError = null;
  if (initializationFailed) {
    // A Keycloak instance cannot be initialized twice. Preserve the editor
    // before reloading so initialization can run again with a fresh instance.
    await redirectAfterPreservingWork(async (url) => { window.location.assign(url); }, "resume");
    return;
  }
  if (!keycloak.authenticated || !keycloak.token) {
    await reconnect();
    return;
  }
  // Import on demand to keep auth state independent of the refresh service.
  const { getValidAccessToken } = await import("./tokenRefresh");
  await getValidAccessToken();
}
