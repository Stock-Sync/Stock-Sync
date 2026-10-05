import { createContext, use } from "react";
import type { User } from "../types/user";

/**
 * Contexto e hook consumidos no lugar do provider.
 *
 * Ficam em arquivos separados de `AuthProvider.tsx` porque a regra
 * `react-refresh/only-export-components` proíbe exportar hooks junto de
 * componentes no mesmo módulo.
 */
export interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = use(AuthContext);
  if (!context) {
    throw new Error("useAuth precisa estar dentro de <AuthProvider>.");
  }
  return context;
}