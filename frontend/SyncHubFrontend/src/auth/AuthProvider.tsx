import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, ERROR_CODES } from "../types/api";
import type { User } from "../types/user";
import { AuthContext } from "./auth-context";
import type { AuthContextValue } from "./auth-context";
import { authClient } from "../lib/api/auth-client";

/**
 * Provedor de autenticação real.
 * 
 * Usa cookies HTTP-only para armazenar tokens (access_token, refresh_token).
 * O estado do usuário é mantido em memória e sincronizado com o backend via /me.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Carrega usuário atual na inicialização
  useEffect(() => {
    const loadUser = async () => {
      try {
        const userData = await authClient.me();
        setUser({
          id: userData.id,
          username: userData.name,
          email: userData.email,
        });
      } catch {
        // Usuário não autenticado - isso é normal
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };

    loadUser();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const trimmedEmail = email.trim();

    if (trimmedEmail.length === 0) {
      throw new ApiError(
        ERROR_CODES.validationError,
        "Informe o e-mail."
      );
    }
    if (password.length === 0) {
      throw new ApiError(
        ERROR_CODES.validationError,
        "Informe a senha."
      );
    }

    const userData = await authClient.login({ email: trimmedEmail, password });
    
    const session: User = {
      id: userData.id,
      username: userData.name,
      email: userData.email,
    };
    setUser(session);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authClient.logout();
    } catch {
      // Ignora erros de logout - limpa estado local mesmo assim
    }
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, isAuthenticated: user !== null, login, logout, isLoading }),
    [user, login, logout, isLoading]
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}