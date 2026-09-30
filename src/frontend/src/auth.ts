import { AuthTokenResponse, AuthUser } from "./types";
import { isDemoMode, handleDemoApiRequest } from "./demoData";

export { isDemoMode };

const TOKEN_KEY = "caelum_jwt_token";
const USER_KEY = "caelum_user_profile";

export function getAuthToken(): string | null {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) return token;
  if (isDemoMode()) return "demo-mock-jwt-token";
  return null;
}

export function getCurrentUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (raw) {
    try {
      return JSON.parse(raw) as AuthUser;
    } catch {
      // ignore
    }
  }
  if (isDemoMode()) {
    return {
      id: "analyst_viper",
      username: "analyst_viper",
      role: "analyst",
    };
  }
  return null;
}

export function setAuthSession(data: AuthTokenResponse): void {
  localStorage.setItem(TOKEN_KEY, data.access_token);
  const user: AuthUser = {
    id: data.username,
    username: data.username,
    role: data.role,
  };
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuthSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

/**
 * Fetch wrapper that attaches the JWT Bearer token to all outgoing requests
 * and redirects to unauthenticated state upon HTTP 401.
 *
 * In Demo Mode, transparently routes API calls to static demo JSON payloads
 * and maintains in-memory optimistic updates.
 */
export async function authFetch(
  url: string,
  options: RequestInit = {},
  onUnauthorized?: () => void,
): Promise<Response> {
  if (isDemoMode()) {
    try {
      return await handleDemoApiRequest(url, options);
    } catch (err) {
      console.warn(
        "Demo API dispatch failed, falling back to network fetch",
        err,
      );
    }
  }

  const token = getAuthToken();
  const headers = new Headers(options.headers || {});

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    clearAuthSession();
    if (onUnauthorized) {
      onUnauthorized();
    }
  }

  return response;
}
