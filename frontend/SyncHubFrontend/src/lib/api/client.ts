import type { PlatformMapping, SKU, Product, ProductCreate, SKUCreate } from "../../types/catalog";
import type { Order, Store, StoreCreate, Notification } from "../../types/entities";
import { ERROR_CODES, ApiError } from "../../types/api";

/**
 * Contrato do cliente de dados.
 *
 * Telas e hooks nunca importam o mock diretamente — dependem apenas deste mapa
 * de operações. Para migrar para o backend real, implemente cada método com
 * `fetch`/axios contra os endpoints do catalog-service, preservando as mesmas
 * Promises e o mesmo `ApiError` (o envelope de erro já segue o formato de
 * `app/api/handlers.py` em cada serviço).
 *
 * Endpoints alvo:
 *   products  → GET/POST /products, GET/PUT/DELETE /products/{id}
 *   skus      → GET/POST /skus, GET/PUT/DELETE /skus/{id}
 *   listings  → GET/POST /platform-mappings
 */
export interface ApiClient {
  products: {
    list(): Promise<Product[]>;
    create(payload: ProductCreate): Promise<Product>;
    update(id: number, payload: Partial<ProductCreate>): Promise<Product>;
    remove(id: number): Promise<void>;
  };
  skus: {
    list(): Promise<SKU[]>;
    create(payload: SKUCreate): Promise<SKU>;
    update(id: number, payload: Partial<SKUCreate>): Promise<SKU>;
    remove(id: number): Promise<void>;
  };
  listings: {
    list(): Promise<PlatformMapping[]>;
    createForSku(skuId: number): Promise<PlatformMapping>;
    remove(id: number): Promise<void>;
  };
  stores: {
    list(): Promise<Store[]>;
    create(payload: StoreCreate): Promise<Store>;
    remove(id: number): Promise<void>;
  };
  orders: {
    list(): Promise<Order[]>;
  };
  notifications: {
    list(): Promise<Notification[]>;
    markAllAsRead(): Promise<void>;
  };
  sync: {
    runAll(): Promise<number>;
  };
}

/**
 * Latência artificial para simular rede. Remover junto com a implementação
 * mock; mantido baixo para não atrasar o desenvolvimento.
 */
export const NETWORK_DELAY_MS = 180;

export function delay<T>(value: T, ms = NETWORK_DELAY_MS): Promise<T> {
  return new Promise((resolve) => {
    setTimeout(() => resolve(value), ms);
  });
}

export function notFound(entity: string, id: number): ApiError {
  return new ApiError(
    ERROR_CODES.notFound,
    `${entity} ${id} não encontrado.`
  );
}