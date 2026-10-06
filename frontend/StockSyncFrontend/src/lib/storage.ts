const PREFIX = "stocksync";

export const storageKeys = {
  session: `${PREFIX}:session`,
  products: `${PREFIX}:products`,
  skus: `${PREFIX}:skus`,
  listings: `${PREFIX}:listings`,
  stores: `${PREFIX}:stores`,
  orders: `${PREFIX}:orders`,
  notifications: `${PREFIX}:notifications`,
} as const;

/**
 * Leitura segura do localStorage.
 *
 * Retorna `null` quando o valor não existe ou o JSON está corrompido, em vez
 * de lançar — um estado de storage inválido não deve derrubar a aplicação.
 */
export function readStorage<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) {
      return null;
    }
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function writeStorage<T>(key: string, value: T): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage indisponível (modo privado, quota excedida). A UI segue em
    // memória; apenas não há persistência entre recarregamentos.
  }
}

export function removeStorage(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Ver writeStorage.
  }
}