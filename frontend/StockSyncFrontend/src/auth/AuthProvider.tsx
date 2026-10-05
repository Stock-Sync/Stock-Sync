import { useCallback, useMemo, useState, type ReactNode } from "react";
import { ApiError, ERROR_CODES } from "../types/api";
import type { User } from "../types/user";
import { readStorage, removeStorage, storageKeys, writeStorage } from "../lib/storage";
import { clearPersisted } from "../mock/handlers";
import { AuthContext } from "./auth-context";
import type { AuthContextValue } from "./auth-context";

/**
 * Sessão mockada.
 *
 * Não existe autenticação no backend: qualquer par usuário/senha não-vazio
 * cria uma sessão local. A troca por auth real deve acontecer inteiramente
 * dentro deste provider — `login` passa a chamar o endpoint e a devolver o
 * `User`, e nada mais na aplicação muda.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(
    () => readStorage<User>(storageKeys.session)
  );

  const login = useCallback(async (username: string, password: string) => {
    const trimmedUsername = username.trim();

    if (trimmedUsername.length === 0) {
      throw new ApiError(
        ERROR_CODES.validationError,
        "Informe o nome de usuário."
      );
    }
    if (password.length === 0) {
      throw new ApiError(
        ERROR_CODES.validationError,
        "Informe a senha."
      );
    }

    const session: User = {
      id: 1,
      username: trimmedUsername,
      // O mock de perfil exibe o email vazio (Imagem 7).
      email: "",
    };
    writeStorage(storageKeys.session, session);
    setUser(session);
  }, []);

  const logout = useCallback(() => {
    removeStorage(storageKeys.session);
    setUser(null);
    // Descarta também os dados mockados: o próximo usuário não deve herdar o
    // catálogo de quem saiu.
    clearPersisted();
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, isAuthenticated: user !== null, login, logout }),
    [user, login, logout]
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}