import { httpClient } from "./http-client";

export interface Product {
  id: number;
  tenant_id: string;
  name: string;
  description: string | null;
  pictures?: string[];
  created_at: string;
  updated_at: string;
}

export interface ProductCreate {
  name: string;
  description?: string;
  pictures?: string[];
}

export interface ProductUpdate {
  name?: string;
  description?: string;
  pictures?: string[];
}

export interface SKU {
  id: number;
  tenant_id: string;
  product_id: number;
  internal_sku: string;
  price: number;
  stock_quantity: number;
  created_at: string;
  updated_at: string;
}

export interface SKUCreate {
  product_id: number;
  internal_sku: string;
  price: number;
  stock_quantity: number;
}

export interface SKUUpdate {
  internal_sku?: string;
  price?: number;
  stock_quantity?: number;
}

/** Dados para criação de um anúncio local (vínculo produto ↔ marketplace). */
export interface PlatformMappingCreate {
  sku_id: number;
  platform: "mercado_livre" | "shopee";
  platform_sku: string;
  platform_product_id?: string | null;
  is_active?: boolean;
}

export interface PlatformMapping {
  id: number;
  tenant_id: string;
  sku_id: number;
  platform: "mercado_livre" | "shopee";
  platform_sku: string;
  platform_product_id: string | null;
  platform_variant_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const CATALOG_BASE = "/api/v1";

export const catalogClient = {
  // Products
  async listProducts(): Promise<Product[]> {
    return httpClient.get<Product[]>(`${CATALOG_BASE}/products`);
  },

  async createProduct(payload: ProductCreate): Promise<Product> {
    return httpClient.post<Product>(`${CATALOG_BASE}/products`, payload);
  },

  async updateProduct(id: number, payload: ProductUpdate): Promise<Product> {
    return httpClient.put<Product>(`${CATALOG_BASE}/products/${id}`, payload);
  },

  async deleteProduct(id: number): Promise<void> {
    return httpClient.delete<void>(`${CATALOG_BASE}/products/${id}`);
  },

  // SKUs
  async listSkus(): Promise<SKU[]> {
    return httpClient.get<SKU[]>(`${CATALOG_BASE}/skus`);
  },

  async createSku(payload: SKUCreate): Promise<SKU> {
    return httpClient.post<SKU>(`${CATALOG_BASE}/skus`, payload);
  },

  async updateSku(id: number, payload: SKUUpdate): Promise<SKU> {
    return httpClient.put<SKU>(`${CATALOG_BASE}/skus/${id}`, payload);
  },

  async deleteSku(id: number): Promise<void> {
    return httpClient.delete<void>(`${CATALOG_BASE}/skus/${id}`);
  },

  // Products (lookup)
  async getProduct(id: number): Promise<Product> {
    return httpClient.get<Product>(`${CATALOG_BASE}/products/${id}`);
  },

  // SKUs (lookup)
  async getSku(id: number): Promise<SKU> {
    return httpClient.get<SKU>(`${CATALOG_BASE}/skus/${id}`);
  },

  // Platform Mappings (Listings) - vínculos locais produto ↔ marketplace
  async listPlatformMappings(): Promise<PlatformMapping[]> {
    return httpClient.get<PlatformMapping[]>(`${CATALOG_BASE}/platform-mappings`);
  },

  async getPlatformMapping(id: number): Promise<PlatformMapping> {
    return httpClient.get<PlatformMapping>(
      `${CATALOG_BASE}/platform-mappings/${id}`
    );
  },

  async createPlatformMapping(
    payload: PlatformMappingCreate
  ): Promise<PlatformMapping> {
    return httpClient.post<PlatformMapping>(
      `${CATALOG_BASE}/platform-mappings`,
      payload
    );
  },

  async deletePlatformMapping(id: number): Promise<void> {
    return httpClient.delete<void>(
      `${CATALOG_BASE}/platform-mappings/${id}`
    );
  },
};