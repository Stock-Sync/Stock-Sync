import { httpClient } from "./http-client";

/** Categoria do site do Mercado Livre (navegação em árvore). */
export interface MlSiteCategory {
  id: string;
  name: string;
}

/** Detalhe de uma categoria, incluindo filhas, para validação de nó folha. */
export interface MlCategoryDetail {
  id: string;
  name: string;
  children_categories: Array<{ id: string; name: string }>;
}

/** Atributo de categoria retornado pelo Mercado Livre. */
export interface MlCategoryAttribute {
  id: string;
  name: string;
  type: string; // "string", "number", "list", "boolean"
  value_type: string;
  required: boolean;
  min_length?: number;
  max_length?: number;
  min_value?: number;
  max_value?: number;
  /** Unidade de atributos numéricos (ex.: "Centímetros", "Gramos"). */
  number_unit?: string | null;
  allowed_values?: Array<{ id: string; name: string; hidden?: boolean }>;
  allowed_units?: Array<{ id: string; name: string }>;
  tags?: Record<string, unknown>; // { required, catalog_required, ... }
  [key: string]: unknown; // demais metadados repassados pelo proxy
}

/** Resposta da criação de item no Mercado Livre (v3). */
export interface MlItemResponse {
  id: string; // ex.: MLB12345678
  title: string;
  status: string;
  permalink?: string;
  thumbnail?: string;
  price?: number;
  available_quantity?: number;
  listing_type_id?: string;
  condition?: string;
  category_id?: string;
  pictures?: Array<{ secure_url: string }>;
  attributes?: Array<{ id: string; value_name: string; value_id: string | null }>;
  /** Cloudinary URLs persistidas localmente para reedição. */
  _cloudinary_urls?: string[];
}

/** Payload para criação de item (POST /items). */
export interface CreateMlItemRequest {
  /** @deprecated Use family_name. Mercado Livre v3 only accepts family_name. 
   *  Kept for backwards compatibility - backend may map title → family_name. */
  title?: string; 
  category_id: string; // deve ser nó folha
  family_name: string;
  listing_type_id: "gold_pro" | "gold_special";
  condition: "new" | "used";
  currency_id: "BRL";
  buying_mode?: "buy_it_now" | "auction" | "classified";
  price: number;
  available_quantity: number;
  pictures: Array<{ source: string }>;
  attributes: Array<{ id: string; value_name?: string; value_id?: string }>;
  sale_terms?: Array<{ id: string; value_name?: string; value_id?: string }>;
  /** Enviada em chamada separada (POST /items/{id}/description) pelo proxy. */
  description?: string;
  /** Vínculo com o catálogo interno (products-service). */
  sku_id?: number;
  product_id?: number;
}

/** Payload para atualização de item existente (campos editáveis). */
export interface UpdateMlItemRequest {
  title?: string;
  price?: number;
  available_quantity?: number;
  status?: "active" | "paused" | "closed";
  pictures?: Array<{ source: string }>;
  description?: string;
  attributes?: Array<{ id: string; value_name: string; value_id?: string }>;
  sale_terms?: Array<{ id: string; value_name: string; value_id?: string }>;
  children?: Array<{
    attributes: Array<{ id: string; value_name: string; value_id?: string }>;
    available_quantity: number;
    price: number;
    seller_custom_field?: string;
    pictures?: Array<{ source: string }>;
  }>;
}

const ML_BASE = "/api/v1/integrations/mercadolivre";

export const mercadolibreClient = {
  /** Lista as categorias raiz do site (GET /sites/MLB/categories). */
  async listSiteCategories(): Promise<MlSiteCategory[]> {
    return httpClient.get<MlSiteCategory[]>(`${ML_BASE}/categories`);
  },

  /** Detalhe de uma categoria, incluindo filhas (GET /categories/{id}) — fallback em árvore. */
  async getCategory(categoryId: string): Promise<MlCategoryDetail> {
    return httpClient.get<MlCategoryDetail>(
      `${ML_BASE}/categories/${categoryId}`
    );
  },

  /** Atributos técnicos de uma categoria (GET /categories/{id}/attributes). */
  async getCategoryAttributes(
    categoryId: string
  ): Promise<MlCategoryAttribute[]> {
    return httpClient.get<MlCategoryAttribute[]>(
      `${ML_BASE}/categories/${categoryId}/attributes`
    );
  },

  /** Cria o anúncio no Mercado Livre (POST /items) e retorna o ID gerado (ex.: MLB12345678). */
  async createMlItem(
    payload: CreateMlItemRequest
  ): Promise<MlItemResponse> {
    return httpClient.post<MlItemResponse>(`${ML_BASE}/items`, payload);
  },

  /** Atualiza um anúncio existente (PUT /items/{id}). */
  async updateMlItem(
    itemId: string,
    payload: UpdateMlItemRequest
  ): Promise<MlItemResponse> {
    return httpClient.put<MlItemResponse>(
      `${ML_BASE}/items/${itemId}`,
      payload
    );
  },

  /** Detalhe de um item publicado (GET /items/{id}). */
  async getMlItem(itemId: string): Promise<MlItemResponse> {
    return httpClient.get<MlItemResponse>(`${ML_BASE}/items/${itemId}`);
  },

  /** Cria/substituí a descrição do anúncio (POST /items/{id}/description, v3). */
  async createMlItemDescription(
    itemId: string,
    plainText: string
  ): Promise<{ message?: string }> {
    return httpClient.post<{ message?: string }>(
      `${ML_BASE}/items/${itemId}/description`,
      { plain_text: plainText }
    );
  },
};
