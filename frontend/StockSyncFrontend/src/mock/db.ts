import type { PlatformMapping, SKU, Product } from "../types/catalog";
import { Platform } from "../types/catalog";
import type { Order, Store, Notification } from "../types/entities";

/**
 * Base de dados em memória, semeada a partir dos mockups.
 *
 * Reflete o que as imagens mostram: um produto `rafael` / `Titulo` a R$ 10,00,
 * um usuário `amoras` e nenhuma loja cadastrada. Os registros são clonados na
 * leitura para que a UI nunca mutar o seed (React Query trata o resultado como
 * imutável).
 */

const productSeed: Product[] = [
  {
    id: 1,
    name: "Titulo",
    description: "produto rafa",
    created_at: "2026-09-19T13:02:00.000Z",
    updated_at: "2026-09-19T13:02:00.000Z",
  },
];

const skuSeed: SKU[] = [
  {
    id: 1,
    product_id: 1,
    internal_sku: "rafael",
    price: 10,
    stock_quantity: 0,
    created_at: "2026-09-19T13:02:00.000Z",
    updated_at: "2026-09-19T13:02:00.000Z",
  },
];

const listingSeed: PlatformMapping[] = [];

const storeSeed: Store[] = [];

const orderSeed: Order[] = [
  {
    id: 1,
    marketplace: "Shopee",
    marketplace_order_id: "SH-882134",
    internal_sku: "rafael",
    quantity: 2,
    total_amount: 20,
    currency: "BRL",
    status: "paid",
    ordered_at: "2026-09-19T09:14:00.000Z",
    created_at: "2026-09-19T09:14:00.000Z",
  },
];

const notificationSeed: Notification[] = [];

function clone<T>(value: T): T {
  return structuredClone(value);
}

export interface MockDatabase {
  products: Product[];
  skus: SKU[];
  listings: PlatformMapping[];
  stores: Store[];
  orders: Order[];
  notifications: Notification[];
}

export const seedDatabase = (): MockDatabase => ({
  products: clone(productSeed),
  skus: clone(skuSeed),
  listings: clone(listingSeed),
  stores: clone(storeSeed),
  orders: clone(orderSeed),
  notifications: clone(notificationSeed),
});

/**
 * Estado global do mock.
 *
 * Sobrevive ao unmount das telas mas não a um reload — a persistência em
 * localStorage acontece na camada de sincronização.
 */
export const db: MockDatabase = seedDatabase();

/** Restaurar o estado inicial — usado pelos testes. */
export function resetDatabase(): void {
  const fresh = seedDatabase();
  db.products = fresh.products;
  db.skus = fresh.skus;
  db.listings = fresh.listings;
  db.stores = fresh.stores;
  db.orders = fresh.orders;
  db.notifications = fresh.notifications;
}

let nextId = 1000;

/** IDs sequenciais, acima dos seeds, para evitar colisão. */
export function nextEntityId(): number {
  nextId += 1;
  return nextId;
}

export const nowIso = (): string => new Date().toISOString();

/** Plataformas alternadas ao gerar anúncios, para variar o mock. */
export const platforms: Platform[] = [Platform.mercadolivre, Platform.shopee];