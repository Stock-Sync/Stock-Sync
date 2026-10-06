import { ERROR_CODES, ApiError } from "../types/api";
import type { PlatformMapping, SKU, Product, ProductCreate, SKUCreate } from "../types/catalog";
import type { Store, StoreCreate, Notification } from "../types/entities";
import type { ApiClient } from "../lib/api/client";
import { delay, notFound } from "../lib/api/client";
import { storageKeys, readStorage, writeStorage, removeStorage } from "../lib/storage";
import { db, nextEntityId, nowIso, platforms } from "./db";

/**
 * Implementação mockada do `ApiClient`.
 *
 * Lê e escreve no `db` (memória) e persiste cada coleção em localStorage, de
 * modo que criar/editar um produto sobreviva a um recarregamento — necessário
 * para reproduzir o fluxo das Imagens 3 → 4 → 5.
 */

// ---------------------------------------------------------------------------
// Persistência
// ---------------------------------------------------------------------------

interface PersistedState {
  products: Product[];
  skus: SKU[];
  listings: PlatformMapping[];
  stores: Store[];
  notifications: Notification[];
}

function persist(): void {
  const state: PersistedState = {
    products: db.products,
    skus: db.skus,
    listings: db.listings,
    stores: db.stores,
    notifications: db.notifications,
  };
  writeStorage(storageKeys.products, state.products);
  writeStorage(storageKeys.skus, state.skus);
  writeStorage(storageKeys.listings, state.listings);
  writeStorage(storageKeys.stores, state.stores);
  writeStorage(storageKeys.notifications, state.notifications);
}

/** Hidrata o `db` a partir do localStorage, se houver dados salvos. */
export function hydrate(): void {
  const products = readStorage<Product[]>(storageKeys.products);
  const skus = readStorage<SKU[]>(storageKeys.skus);
  const listings = readStorage<PlatformMapping[]>(storageKeys.listings);
  const stores = readStorage<Store[]>(storageKeys.stores);
  const notifications = readStorage<Notification[]>(storageKeys.notifications);

  if (products) {
    db.products = products;
  }
  if (skus) {
    db.skus = skus;
  }
  if (listings) {
    db.listings = listings;
  }
  if (stores) {
    db.stores = stores;
  }
  if (notifications) {
    db.notifications = notifications;
  }
}

/** Limpa todos os dados mockados (usado pelo logout e pelos testes). */
export function clearPersisted(): void {
  removeStorage(storageKeys.products);
  removeStorage(storageKeys.skus);
  removeStorage(storageKeys.listings);
  removeStorage(storageKeys.stores);
  removeStorage(storageKeys.notifications);
}

const clone = <T,>(value: T): T => structuredClone(value);

// ---------------------------------------------------------------------------
// Validação
// ---------------------------------------------------------------------------

function assertNonEmpty(value: string, field: string): void {
  if (value.trim().length === 0) {
    throw new ApiError(
      ERROR_CODES.validationError,
      `O campo ${field} é obrigatório.`
    );
  }
}

function assertUniqueSku(internalSku: string, ignoreSkuId?: number): void {
  const duplicate = db.skus.find(
    (sku) =>
      sku.internal_sku.toLowerCase() === internalSku.toLowerCase() &&
      sku.id !== ignoreSkuId
  );
  if (duplicate) {
    throw new ApiError(
      ERROR_CODES.conflict,
      `Já existe um produto com o SKU "${internalSku}".`
    );
  }
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export const mockApi: ApiClient = {
  products: {
    list: () => delay(clone(db.products)),

    create: (payload: ProductCreate) => {
      assertNonEmpty(payload.name, "Title");
      const product: Product = {
        id: nextEntityId(),
        name: payload.name.trim(),
        description: payload.description ? payload.description.trim() : null,
        created_at: nowIso(),
        updated_at: nowIso(),
      };
      db.products.push(product);
      persist();
      return delay(clone(product));
    },

    update: (id: number, payload: Partial<ProductCreate>) => {
      const product = db.products.find((item) => item.id === id);
      if (!product) {
        throw notFound("Produto", id);
      }
      if (payload.name !== undefined) {
        assertNonEmpty(payload.name, "Title");
        product.name = payload.name.trim();
      }
      if (payload.description !== undefined) {
        const description = payload.description;
        product.description = description ? description.trim() : null;
      }
      product.updated_at = nowIso();
      persist();
      return delay(clone(product));
    },

    /**
     * Remove o produto e tudo que depende dele (SKU e anúncios), espelhando as
     * foreign keys do backend.
     */
    remove: (id: number) => {
      const index = db.products.findIndex((item) => item.id === id);
      if (index === -1) {
        throw notFound("Produto", id);
      }
      const removedSkus = db.skus.filter((sku) => sku.product_id === id);
      const removedSkuIds = removedSkus.map((sku) => sku.id);

      db.products.splice(index, 1);
      db.skus = db.skus.filter((sku) => sku.product_id !== id);
      db.listings = db.listings.filter(
        (listing) => !removedSkuIds.includes(listing.sku_id)
      );
      persist();
      return delay(undefined);
    },
  },

  skus: {
    list: () => delay(clone(db.skus)),

    create: (payload: SKUCreate) => {
      assertNonEmpty(payload.internal_sku, "Sku");
      assertUniqueSku(payload.internal_sku);
      if (!db.products.some((product) => product.id === payload.product_id)) {
        throw notFound("Produto", payload.product_id);
      }
      const sku: SKU = {
        id: nextEntityId(),
        product_id: payload.product_id,
        internal_sku: payload.internal_sku.trim(),
        price: payload.price,
        stock_quantity: payload.stock_quantity,
        created_at: nowIso(),
        updated_at: nowIso(),
      };
      db.skus.push(sku);
      persist();
      return delay(clone(sku));
    },

    update: (id: number, payload: Partial<SKUCreate>) => {
      const sku = db.skus.find((item) => item.id === id);
      if (!sku) {
        throw notFound("SKU", id);
      }
      if (payload.internal_sku !== undefined) {
        assertNonEmpty(payload.internal_sku, "Sku");
        assertUniqueSku(payload.internal_sku, id);
        sku.internal_sku = payload.internal_sku.trim();
      }
      if (payload.price !== undefined) {
        sku.price = payload.price;
      }
      if (payload.stock_quantity !== undefined) {
        sku.stock_quantity = payload.stock_quantity;
      }
      sku.updated_at = nowIso();
      persist();
      return delay(clone(sku));
    },

    remove: (id: number) => {
      const index = db.skus.findIndex((item) => item.id === id);
      if (index === -1) {
        throw notFound("SKU", id);
      }
      db.skus.splice(index, 1);
      db.listings = db.listings.filter((listing) => listing.sku_id !== id);
      persist();
      return delay(undefined);
    },
  },

  listings: {
    list: () => delay(clone(db.listings)),

    /**
     * Cria um anúncio para um SKU. Se o SKU já tiver anúncio na plataforma,
     * devolve o existente em vez de duplicar.
     */
    createForSku: (skuId: number) => {
      const sku = db.skus.find((item) => item.id === skuId);
      if (!sku) {
        throw notFound("SKU", skuId);
      }
      const existing = db.listings.find(
        (listing) => listing.sku_id === skuId && listing.is_active
      );
      if (existing) {
        return delay(clone(existing));
      }

      const listing: PlatformMapping = {
        id: nextEntityId(),
        sku_id: skuId,
        platform: platforms[db.listings.length % platforms.length],
        platform_sku: `${sku.internal_sku}-${nextEntityId()}`,
        platform_product_id: String(nextEntityId()),
        platform_variant_id: String(nextEntityId()),
        is_active: true,
        created_at: nowIso(),
        updated_at: nowIso(),
      };
      db.listings.push(listing);
      persist();
      return delay(clone(listing));
    },

    remove: (id: number) => {
      const index = db.listings.findIndex((item) => item.id === id);
      if (index === -1) {
        throw notFound("Anúncio", id);
      }
      db.listings.splice(index, 1);
      persist();
      return delay(undefined);
    },
  },

  stores: {
    list: () => delay(clone(db.stores)),

    create: (payload: StoreCreate) => {
      assertNonEmpty(payload.name, "Name");
      assertNonEmpty(payload.marketplace, "Marketplace");
      assertNonEmpty(payload.external_id, "External id");
      const store: Store = {
        id: nextEntityId(),
        name: payload.name.trim(),
        marketplace: payload.marketplace,
        external_id: payload.external_id.trim(),
        owner_id: payload.owner_id,
        created_at: nowIso(),
        updated_at: nowIso(),
      };
      db.stores.push(store);
      persist();
      return delay(clone(store));
    },

    remove: (id: number) => {
      const index = db.stores.findIndex((item) => item.id === id);
      if (index === -1) {
        throw notFound("Loja", id);
      }
      db.stores.splice(index, 1);
      persist();
      return delay(undefined);
    },
  },

  orders: {
    list: () => delay(clone(db.orders)),
  },

  notifications: {
    list: () => delay(clone(db.notifications)),

    markAllAsRead: () => {
      db.notifications.forEach((notification) => {
        notification.is_read = true;
      });
      persist();
      return delay(undefined);
    },
  },

  /**
   * Simula "Sincronizar Tudo": cria anúncios para todo SKU ativo que ainda não
   * possui um. Devolve quantos anúncios foram gerados.
   */
  sync: {
    runAll: async () => {
      let created = 0;
      for (const sku of db.skus) {
        const alreadyListed = db.listings.some(
          (listing) => listing.sku_id === sku.id && listing.is_active
        );
        if (alreadyListed) {
          continue;
        }
        const listing: PlatformMapping = {
          id: nextEntityId(),
          sku_id: sku.id,
          platform: platforms[db.listings.length % platforms.length],
          platform_sku: `${sku.internal_sku}-${nextEntityId()}`,
          platform_product_id: String(nextEntityId()),
          platform_variant_id: String(nextEntityId()),
          is_active: true,
          created_at: nowIso(),
          updated_at: nowIso(),
        };
        db.listings.push(listing);
        created += 1;
      }
      persist();
      return delay(created);
    },
  },
};

/**
 * Client ativo da aplicação.
 *
 * Ponto único de troca: quando o backend real existir, substitua esta linha
 * por uma implementação HTTP de `ApiClient`. Nenhuma tela precisa mudar.
 */
export const api: ApiClient = mockApi;