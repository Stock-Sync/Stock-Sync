import type { SKU, Product } from "./catalog";

/**
 * Camada de visão: é o formato que as telas realmente consomem.
 *
 * O backend separa Product (name, description) de SKU (internal_sku, price),
 * mas as telas de produto mostram tudo em um registro só — SKU, título,
 * descrição e preço juntos. `toProductView` faz esse achatamento.
 */
export interface ProductView {
  id: number;
  productId: number;
  skuId: number;
  sku: string;
  title: string;
  description: string;
  price: number;
  stockQuantity: number;
  pictures: string[];
  updatedAt: string;
}

export function toProductView(product: Product, sku: SKU): ProductView {
  return {
    id: product.id,
    productId: product.id,
    skuId: sku.id,
    sku: sku.internal_sku,
    title: product.name,
    description: product.description ?? "",
    price: sku.price ?? 0,
    stockQuantity: sku.stock_quantity,
    pictures: product.pictures ?? [],
    updatedAt: sku.updated_at,
  };
}

/** Tipos para anúncios (Mercado Livre v3) */
export type MercadoLivreListingType = "gold_pro" | "gold_special";
export type MercadoLivreCondition = "new" | "used";
export type MercadoLivreCurrency = "BRL";

export interface MercadoLivreAttribute {
  id: string;
  value_name: string;
  value_id?: string;
}

export interface MercadoLivrePicture {
  source: string; // Cloudinary URL
}

export interface MercadoLivreSaleTerm {
  id: string;
  value_name: string;
  value_id?: string;
}

export interface MercadoLivreChild {
  attributes: MercadoLivreAttribute[];
  available_quantity: number;
  price: number;
  seller_custom_field?: string;
  pictures?: MercadoLivrePicture[];
}

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
  attributes: MercadoLivreAttribute[];
  sale_terms?: MercadoLivreSaleTerm[];
  children: MercadoLivreChild[];
}

/** Tipos de atributo do Mercado Livre */
export interface MercadoLivreAttribute {
  id: string;
  name: string;
  type: string; // "string", "number", "list", "boolean"
  value_type: string;
  required: boolean;
  min_length?: number;
  max_length?: number;
  allowed_values?: { id: string; name: string }[];
  tags?: Record<string, any>;
}

/** Tipos de venda para Mercado Livre */
export interface MercadoLivreSaleTerm {
  id: string;
  value_name: string;
  value_id?: string;
}

/** Campos do formulário "Criar Produto" (Imagem 3) - Apenas dados internos do produto */
export interface ProductFormValues {
  // Campos básicos do produto (apenas dados internos)
  sku: string;
  title: string;
  description: string;
  price: string;
  stockQuantity: string;
  
  // Imagens (galeria base do produto)
  pictures: { source: string }[];
}

export const EMPTY_PRODUCT_FORM: ProductFormValues = {
  sku: "",
  title: "",
  description: "",
  price: "",
  stockQuantity: "",
  pictures: [],
};

/** Campos do formulário "Criar Loja" (Imagem 9). */
export interface StoreFormValues {
  name: string;
  marketplace: string;
  externalId: string;
  ownerId: string;
}

export const EMPTY_STORE_FORM: StoreFormValues = {
  name: "",
  marketplace: "",
  externalId: "",
  ownerId: "",
};