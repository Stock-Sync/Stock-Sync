import { httpClient } from "./http-client";

export interface Order {
  id: number;
  marketplace: string;
  marketplace_order_id: string;
  internal_sku: string;
  quantity: number;
  total_amount: number;
  currency: string;
  status: string;
  ordered_at: string;
  created_at: string;
}

export const salesClient = {
  async listOrders(): Promise<Order[]> {
    return httpClient.get<Order[]>("/api/v1/orders");
  },
};