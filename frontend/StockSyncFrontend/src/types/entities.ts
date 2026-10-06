/**
 * Entidades que ainda NÃO existem no backend.
 *
 * Elas existem apenas na camada de dados mockada. Quando o backend passar a
 * expor esses recursos, substitua o mock pelos endpoints reais e mantenha
 * estes tipos como espelho dos novos schemas.
 */

/** "Loja" do usuário — integração com um marketplace. */
export interface Store {
  id: number;
  name: string;
  marketplace: string;
  external_id: string;
  owner_id: number;
  created_at: string;
  updated_at: string;
}

export interface StoreCreate {
  name: string;
  marketplace: string;
  external_id: string;
  owner_id: number;
}

/** Espelha `sales-service/app/models/order.py`. */
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

export interface Notification {
  id: number;
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
}