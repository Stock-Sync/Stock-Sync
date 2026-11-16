import { httpClient } from "./http-client";

export interface MarketplaceCredential {
  id: number;
  tenant_id: string;
  marketplace: "mercado_livre" | "shopee";
  account_name: string;
  ml_user_id: number | null;
  access_token: string;
  refresh_token: string | null;
  expires_at: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateListingAttribute {
  id: string;
  value_name?: string;
  value_id?: string;
  value_struct?: { number: number; unit?: string } | null;
}

export interface CreateListingPayload {
  title?: string | null;
  category_id: string;
  family_name?: string | null;
  listing_type_id?: "gold_pro" | "gold_special";
  condition?: "new" | "used";
  currency_id?: "BRL";
  buying_mode?: "buy_it_now" | "auction" | "classified";
  price: number;
  available_quantity: number;
  pictures: Array<{ source: string }>;
  attributes?: CreateListingAttribute[];
  sale_terms?: Array<{ id: string; value_name?: string; value_id?: string }>;
  description?: string | null;
  /** SKU interno que originou o anúncio. */
  sku_id: number;
  product_id?: number | null;
  /** SKU interno legível usado como platform_sku no vínculo local. */
  platform_sku?: string | null;
}

export interface CreatedListingItem {
  id: string;
  item_id?: string;
  title?: string;
  available_quantity?: number;
  price?: number;
  status?: string | null;
  permalink?: string | null;
  sku_id?: number | null;
  product_id?: number | null;
  [key: string]: unknown;
}

export interface CreateListingResponse {
  item: CreatedListingItem;
  mapping: Record<string, unknown> | null;
  /** true quando a chamada devolveu um anúncio já publicado (retry idempotente). */
  existing: boolean;
}

export interface ConnectResponse {
  auth_url: string;
  tenant_id: string;
}

export interface CallbackResponse {
  message: string;
  credential_id: number;
  ml_user_id: number;
  account_name: string;
}

export interface CredentialResponse {
  id: number;
  marketplace: "mercado_livre" | "shopee";
  account_name: string;
  ml_user_id: number | null;
  ml_nickname: string | null;
  is_active: boolean;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Anúncio importado do Mercado Livre e persistido localmente. */
export interface LocalMarketplaceItem {
  item_id: string;
  title: string;
  price: number;
  available_quantity: number;
  status: string | null;
  /** Espelho do ciclo de vida no ML (active ⇒ true). */
  is_active?: boolean;
  thumbnail: string | null;
  permalink: string | null;
  sku_id: number | null;
  product_id: number | null;
  /** true quando o anúncio possui vínculo local (sku_id). */
  is_mapped?: boolean;
  updated_at: string | null;
  /** Soft-deleted listings are hidden by the API; kept for defensive checks. */
  is_deleted?: boolean;
}

/** Contrato padrão de paginação de `/items/local` (Plan 9). */
export interface PaginatedLocalMarketplaceItems {
  items: LocalMarketplaceItem[];
  page: number;
  limit: number;
  total: number;
  total_pages: number;
}

const ML_BASE = "/api/v1/integrations/mercadolivre";

export const integrationsClient = {
  // Mercado Livre OAuth
  async getMercadoLivreAuthUrl(): Promise<ConnectResponse> {
    return httpClient.get<ConnectResponse>("/api/v1/auth/mercadolivre/connect");
  },

  // Credentials
  async listMercadoLivreCredentials(): Promise<CredentialResponse[]> {
    return httpClient.get<CredentialResponse[]>("/api/v1/integrations/mercadolivre/credentials");
  },

  async deleteMercadoLivreCredential(credentialId: number): Promise<{ message: string }> {
    return httpClient.delete<{ message: string }>(`/api/v1/integrations/mercadolivre/credentials/${credentialId}`);
  },

  // Produtos
  /** Publica anúncio, descrição e vínculos locais em uma única operação. */
  async createListing(payload: CreateListingPayload): Promise<CreateListingResponse> {
    return httpClient.post<CreateListingResponse>(`${ML_BASE}/listings`, payload);
  },

  /**
   * Anúncios importados/sincronizados localmente (MarketplaceItem).
   *
   * O endpoint devolve o contrato paginado (items/page/limit/total/total_pages);
   * a UI atual consome a primeira página como lista simples.
   */
  async listLocalMercadoLivreItems(params?: {
    page?: number;
    limit?: number;
    search?: string;
    unmappedOnly?: boolean;
  }): Promise<LocalMarketplaceItem[]> {
    const query = new URLSearchParams();
    if (params?.page) query.set("page", String(params.page));
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.search) query.set("search", params.search);
    if (params?.unmappedOnly) query.set("unmapped_only", "true");
    const suffix = query.toString() ? `?${query.toString()}` : "";
    const page = await httpClient.get<PaginatedLocalMarketplaceItems>(
      `${ML_BASE}/items/local${suffix}`
    );
    return page.items;
  },

  // Webhooks (called by Mercado Livre, not typically from frontend)
};