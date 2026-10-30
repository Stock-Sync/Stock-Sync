import { ApiError } from "../../types/api";

/**
 * HTTP client for communicating with backend services.
 * Reads access_token from cookie and sends as Authorization header.
 * This avoids issues with cookie forwarding through Vite proxy.
 *
 * Automatic token refresh:
 *  - When a request receives HTTP 401, the client calls POST /api/v1/auth/refresh
 *    (which rotates the refresh cookie and issues a new access token) and retries
 *    the original request exactly once.
 *  - A shared in-flight refresh promise prevents stampedes when multiple requests
 *    expire simultaneously.
 *  - Direct `fetch` is used for the refresh call to avoid a circular import with
 *    `auth-client.ts` (which imports `http-client.ts`).
 */

function getAccessTokenFromCookie(): string | null {
  const cookies = document.cookie.split(";");
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split("=");
    if (name === "access_token") {
      return value;
    }
  }
  return null;
}

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
  /** Internal flag to prevent infinite refresh/retry loops. */
  _retried?: boolean;
}

/** In-flight refresh promise (null when no refresh is happening). */
let refreshPromise: Promise<void> | null = null;

/** Calls the auth-service refresh endpoint to rotate access/refresh cookies. */
async function refreshSession(): Promise<void> {
  const response = await fetch(`${window.location.origin}/api/v1/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    throw new Error(`Refresh failed: ${response.status}`);
  }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { params, headers, _retried, ...fetchOptions } = options;

  // Use relative URL so Vite proxy handles it
  const url = new URL(path, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        url.searchParams.append(key, String(value));
      }
    });
  }

  // Get access token from cookie and add as Authorization header
  const accessToken = getAccessTokenFromCookie();
  const authHeaders: Record<string, string> = {};
  if (accessToken) {
    authHeaders["Authorization"] = `Bearer ${accessToken}`;
  }

  const response = await fetch(url.toString(), {
    ...fetchOptions,
    credentials: "include", // Still include cookies for refresh_token etc.
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      ...headers,
    },
  });

  if (!response.ok) {
    // Automatic token refresh on 401: rotate tokens and retry once.
    if (response.status === 401 && !_retried) {
      if (!refreshPromise) {
        refreshPromise = (async () => {
          try {
            await refreshSession();
          } finally {
            refreshPromise = null;
          }
        })();
      }
      try {
        await refreshPromise;
        // Retry the original request once now that new cookies are set.
        return request<T>(path, { ...options, _retried: true });
      } catch {
        // Refresh failed (e.g. refresh token also expired); fall through to
        // the normal error path below.
      }
    }

    // Formatos de erro tolerados: { error: { code, message, details } } (padrão
    // dos serviços) e { detail: "..." } (HTTPException do FastAPI).
    type ErrorEnvelope = {
      error?: { code?: string; message?: string; details?: unknown };
      detail?: unknown;
    };
    let errorData: ErrorEnvelope;
    try {
      errorData = (await response.json()) as ErrorEnvelope;
    } catch {
      errorData = {
        error: { code: "http_error", message: response.statusText },
      };
    }

    const normalized =
      errorData.error ??
      (errorData.detail !== undefined
        ? {
            code: "http_error",
            message:
              typeof errorData.detail === "string"
                ? errorData.detail
                : JSON.stringify(errorData.detail),
          }
        : undefined);
    throw new ApiError(
      normalized?.code ?? "unknown",
      normalized?.message ?? "Unknown error",
      normalized?.details,
      response.status
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

export const httpClient = {
  get<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
    return request<T>(path, { method: "GET", params });
  },

  post<T>(path: string, body: unknown): Promise<T> {
    return request<T>(path, { method: "POST", body: JSON.stringify(body) });
  },

  put<T>(path: string, body: unknown): Promise<T> {
    return request<T>(path, { method: "PUT", body: JSON.stringify(body) });
  },

  patch<T>(path: string, body: unknown): Promise<T> {
    return request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
  },

  delete<T>(path: string): Promise<T> {
    return request<T>(path, { method: "DELETE" });
  },
};