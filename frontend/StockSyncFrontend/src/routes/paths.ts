/**
 * Caminhos de navegação em um único lugar.
 *
 * Como a aplicação usa HashRouter, toda URL real tem a forma
 * `/#/caminho`. Alterar uma rota aqui a propaga para links, redirecionamentos
 * e testes.
 */
export const paths = {
  dashboard: "/",
  login: "/login",

  products: "/products",
  productNew: "/products/new",
  productDetail: (id: number) => `/products/${id}`,
  productEdit: (id: number) => `/products/${id}/edit`,

  profile: "/profile",

  stores: "/stores",
  storeNew: "/stores/new",

  listings: "/listings",
  orders: "/orders",
} as const;