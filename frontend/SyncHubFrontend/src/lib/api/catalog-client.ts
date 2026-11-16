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

/**
 * DTOs for Plan 11 composite Product+SKU endpoints.
 *
 * Note: ``category_id`` is NOT part of the catalog Product model; it's
 * managed at the marketplace listing level (Plan 12). Included here only
 * for schema completeness because the original plan spec references it.
 */
export interface ProductCompositeCreate {
  name: string;
  description?: string;
  // category_id: string | null = null; // not stored in catalog Product
  internal_sku: string;
  price: number;
  stock_quantity: number;
  pictures?: string[];
}

export interface ProductCompositeUpdate {
  name?: string;
  description?: string;
  // category_id?: string | null;
  internal_sku?: string;
  price?: number;
  stock_quantity?: number;
  pictures?: string[];
}

export interface ProductCompositeRead {
  id: number;
  tenant_id: string;
  name: string;
  description?: string;
  // category_id?: string | null;
  pictures?: string[];
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
  sku: SKU;
}

const CATALOG_BASE = "/api/v1";

export const catalogClient = {
  // Existing endpoints
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

  /**
   * Plan 11: atomic creation of a Product and its single SKU.
   *
   * Unlike the legacy ``/products`` + ``/skus`` pair, this endpoint ensures
   * both rows are written in one transaction so the UI can treat it as a
   * single operation (create product + create sku). If anything fails, the
   * product is rolled back.
   */
  async createProductComposite(payload: ProductCompositeCreate): Promise<ProductCompositeRead> {
    return httpClient.post<ProductCompositeRead>(`${CATALOG_BASE}/products/composite`, payload);
  },

  async updateProductComposite(id: number, payload: ProductCompositeUpdate): Promise<ProductCompositeRead> {
    return httpClient.put<ProductCompositeRead>(`${CATALOG_BASE}/products/${id}/composite`, payload);
  },

  async unbindProductListings(
    id: number
  ): Promise<{ unbound: number; platform_product_ids: string[] }> {
    return httpClient.post<{ unbound: number; platform_product_ids: string[] }>(`${CATALOG_BASE}/products/${id}/unbind-listings`, {});
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
    return httpClient.get<PlatformMapping[]>(
      `${CATALOG_BASE}/platform-mappings`
    );
  },

  async getPlatformMapping(id: number): Promise<PlatformMapping> {
    return httpClient.get<PlatformMapping>(`${CATALOG_BASE}/platform-mappings/${id}`);
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
    return httpClient.delete<void>(`${CATALOG_BASE}/platform-mappings/${id}`);
  },
};