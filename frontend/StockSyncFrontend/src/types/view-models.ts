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
    updatedAt: sku.updated_at,
  };
}

/** Campos do formulário "Criar Produto" (Imagem 3). */
export interface ProductFormValues {
  sku: string;
  title: string;
  description: string;
  price: string;
  stockQuantity: string;
}

export const EMPTY_PRODUCT_FORM: ProductFormValues = {
  sku: "",
  title: "",
  description: "",
  price: "",
  stockQuantity: "",
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