import { useQuery } from "@tanstack/react-query";
import { salesClient } from "../../lib/api/sales-client";

export const orderQueryKeys = {
  orders: ["orders"] as const,
} as const;

export function useOrders() {
  return useQuery({
    queryKey: orderQueryKeys.orders,
    queryFn: () => salesClient.listOrders(),
  });
}