import { httpClient } from "./http-client";

export interface Order {
  id: number;
  marketplace: string;
  marketplace_order_id: string;
  marketplace_item_id: string;
  internal_sku: string | null;
  sku_id: number | null;
  item_title: string | null;
  thumbnail_url: string | null;
  buyer_nickname: string | null;
  quantity: number;
  unit_price: number | null;
  total_amount: number;
  currency: string;
  status: string;
  ordered_at: string;
  created_at: string;
}

export interface OrderListResponse {
  items: Order[];
  total: number;
  page: number;
  limit: number;
}

export interface ListOrdersParams {
  page?: number;
  limit?: number;
}

export const salesClient = {
  async listOrders(params: ListOrdersParams = {}): Promise<OrderListResponse> {
    return httpClient.get<OrderListResponse>("/api/v1/orders", { ...params });
  },
};
