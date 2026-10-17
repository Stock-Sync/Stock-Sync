import { httpClient } from "./http-client";

export interface Store {
  id: number;
  name: string;
  marketplace: string;
  external_id: string;
  owner_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface StoreCreate {
  name: string;
  marketplace: string;
  external_id: string;
  owner_id?: string;
}

export const storesClient = {
  async list(): Promise<Store[]> {
    return httpClient.get<Store[]>("/api/v1/stores");
  },

  async create(payload: StoreCreate): Promise<Store> {
    return httpClient.post<Store>("/api/v1/stores", payload);
  },

  async remove(id: number): Promise<void> {
    return httpClient.delete<void>(`/api/v1/stores/${id}`);
  },
};