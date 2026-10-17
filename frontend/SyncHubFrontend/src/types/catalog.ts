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
} as const;

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
  
  // Mercado Livre v3 fields (armazenados no integrations-service; o
  // catálogo guarda apenas o vínculo básico produto ↔ anúncio)
  family_name?: string | null;
  listing_type_id?: string | null; // "gold_pro" | "gold_special"
  condition?: string | null; // "new" | "used"
  attributes?: MercadoLivreAttribute[] | null;
  children?: MercadoLivreChild[] | null;
  listing_status?: string | null; // active, paused, closed, etc.
}

/** Atributos do Mercado Livre (v3) */
export interface MercadoLivreAttribute {
  id: string;
  name: string;
  value_name: string | null;
  value_id: string | null;
  value_type?: string; // string, number, list, boolean
  required?: boolean;
}

/** Variação (child) no modelo User Products v3 */
export interface MercadoLivreChild {
  attributes: MercadoLivreAttribute[];
  available_quantity: number;
  price: number;
  seller_custom_field?: string;
  pictures?: { source: string }[];
  id?: string; // ID da variação no ML
}

/** Atributos de categoria do Mercado Livre */
export interface MercadoLivreCategoryAttribute {
  id: string;
  name: string;
  type: string; // "string", "number", "list", "boolean"
  value_type: string;
  required: boolean;
  allowed_values?: { id: string; name: string }[];
  tags?: Record<string, any>;
}

/** Termos de venda (garantia, etc.) */
export interface MercadoLivreSaleTerm {
  id: string;
  value_name: string;
  value_id?: string;
}

/** Variação (child) completa para criação/atualização */
export interface MercadoLivreChildCreate {
  attributes: { id: string; value_name: string; value_id?: string }[];
  available_quantity: number;
  price: number;
  seller_custom_field?: string;
  pictures?: { source: string }[];
}

/** Dados para criação de anúncio (User Products v3) */
export interface MercadoLivreListingCreate {
  family_name: string;
  title: string;
  category_id: string;
  listing_type_id: "gold_pro" | "gold_special";
  condition: "new" | "used";
  currency_id: "BRL";
  price: number;
  available_quantity: number;
  pictures: { source: string }[];
  attributes: { id: string; value_name: string; value_id?: string }[];
  sale_terms?: { id: string; value_name: string; value_id?: string }[];
  children: {
    attributes: { id: string; value_name: string; value_id?: string }[];
    available_quantity: number;
    price: number;
    seller_custom_field?: string;
    pictures?: { source: string }[];
  }[];
}

/** Resposta da API de atributos de categoria */
export interface CategoryAttributesResponse {
  category_id: string;
  category_name: string;
  attributes: MercadoLivreCategoryAttribute[];
  cached_at: string;
  expires_at: string;
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

/** Dados para criar um vínculo de anúncio local (produto ↔ marketplace). */
export interface PlatformMappingCreate {
  sku_id: number;
  platform: Platform;
  platform_sku: string;
  platform_product_id?: string | null;
  is_active?: boolean;
}

/** Visão de anúncio usada nas telas de listagem (vínculo enriquecido com o produto). */
export interface ListingView extends PlatformMapping {
  sku: string;
  productTitle: string;
}