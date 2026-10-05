/**
 * Tipos que refletem 1:1 os schemas do catalog-service.
 *
 * Fonte: services/catalog-service/app/schemas/{product,sku,platform_mapping}.py
 * Ao alterar um schema no backend, altere o tipo correspondente aqui.
 *
 * O backend usa `snake_case` e datetimes ISO; mantemos essa convenção para que
 * a troca do mock pelo client HTTP real não exija renomear nada.
 */

export const Platform = {
  mercadolivre: "mercado_livre",
  shopee: "shopee",
} as const;

export type Platform = (typeof Platform)[keyof typeof Platform];

export const PLATFORM_LABELS: Record<Platform, string> = {
  [Platform.mercadolivre]: "Mercado Livre",
  [Platform.shopee]: "Shopee",
};

/** Rótulo exibido de uma plataforma, tolerando valor desconhecido. */
export function platformLabel(value: string): string {
  return PLATFORM_LABELS[value as Platform] ?? value;
}

/** Espelha `ProductRead`. */
export interface Product {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

/** Espelha `SKURead`. */
export interface SKU {
  id: number;
  product_id: number;
  internal_sku: string;
  price: number | null;
  stock_quantity: number;
  created_at: string;
  updated_at: string;
}

/** Espelha `PlatformMappingRead` — é o "anúncio" vinculado a um SKU. */
export interface PlatformMapping {
  id: number;
  sku_id: number;
  platform: Platform;
  platform_sku: string;
  platform_product_id: string | null;
  platform_variant_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductCreate {
  name: string;
  description: string | null;
}

export interface SKUCreate {
  product_id: number;
  internal_sku: string;
  price: number | null;
  stock_quantity: number;
}