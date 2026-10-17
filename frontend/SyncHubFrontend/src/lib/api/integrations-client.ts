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

export interface CreateItemRequest {
  title: string;
  category_id: string;
  price: number;
  currency_id?: string;
  available_quantity: number;
  buying_mode?: string;
  listing_type_id?: string;
  condition?: string;
  description?: string;
  pictures?: Array<{ source: string }>;
  attributes?: Array<{ id: string; value_name: string }>;
}

export interface CreateItemResponse {
  id: string;
  title: string;
  permalink: string;
  status: string;
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
  async createMercadoLivreItem(payload: CreateItemRequest): Promise<CreateItemResponse> {
    return httpClient.post<CreateItemResponse>("/api/v1/integrations/mercadolivre/items", payload);
  },

  // Webhooks (called by Mercado Livre, not typically from frontend)
};