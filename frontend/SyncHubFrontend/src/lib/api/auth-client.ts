import { httpClient } from "./http-client";

export interface User {
  id: string;
  name: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

export interface RegisterRequest {
  name: string;
  email: string;
  password: string;
}

export interface RegisterResponse {
  message: string;
  user_id: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

// Backend returns User directly, not { user: User }
export type LoginResponse = User;

export const authClient = {
  async register(payload: RegisterRequest): Promise<RegisterResponse> {
    return httpClient.post<RegisterResponse>("/api/v1/auth/register", payload);
  },

  async login(payload: LoginRequest): Promise<User> {
    return httpClient.post<User>("/api/v1/auth/login", payload);
  },

  async logout(): Promise<{ message: string }> {
    return httpClient.post<{ message: string }>("/api/v1/auth/logout", {});
  },

  async me(): Promise<User> {
    return httpClient.get<User>("/api/v1/auth/me");
  },

  async refresh(): Promise<{ message: string }> {
    return httpClient.post<{ message: string }>("/api/v1/auth/refresh", {});
  },
};