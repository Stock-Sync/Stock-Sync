import { useQuery } from "@tanstack/react-query";
import { salesClient } from "../../lib/api/sales-client";

export const orderQueryKeys = {
  orders: ["orders"] as const,
  ordersPage: (page: number) => ["orders", page] as const,
} as const;

export interface OrdersQueryOptions {
  page?: number;
  limit?: number;
}

export function useOrders(options: OrdersQueryOptions = {}) {
  const { page = 1, limit = 20 } = options;
  return useQuery({
    queryKey: orderQueryKeys.ordersPage(page),
    queryFn: () => salesClient.listOrders({ page, limit }),
  });
}
