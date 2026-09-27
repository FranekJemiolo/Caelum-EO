import { AuthTokenResponse, AuthUser } from "./types";

const TOKEN_KEY = "caelum_jwt_token";
const USER_KEY = "caelum_user_profile";

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getCurrentUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
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
 */
export async function authFetch(
  url: string,
  options: RequestInit = {},
  onUnauthorized?: () => void,
): Promise<Response> {
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
