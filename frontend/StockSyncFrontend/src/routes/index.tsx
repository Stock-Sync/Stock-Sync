import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { RequireAuth } from "../auth/RequireAuth";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { LoginPage } from "../features/auth/LoginPage";
import { ProductsListPage } from "../features/products/ProductsListPage";
import {
  ProductDetailPage,
} from "../features/products/ProductDetailPage";
import { ProductFormPage } from "../features/products/ProductFormPage";
import { ProfilePage } from "../features/profile/ProfilePage";
import { StoresPage } from "../features/stores/StoresPage";
import { StoreFormPage } from "../features/stores/StoreFormPage";
import { ListingsPage } from "../features/listings/ListingsPage";
import { OrdersPage } from "../features/orders/OrdersPage";
import { paths } from "./paths";

/**
 * Rotas da aplicação.
 *
 * Liberadas sem sessão (comportamento dos mockups 1, 4 e 5):
 *   /               dashboard do visitante
 *   /products       listagem do catálogo
 *   /products/:id   detalhe do produto
 *   /login
 *
 * Protegidas por <RequireAuth>: tudo que cria ou edita dados, além do perfil,
 * das lojas, dos anúncios e dos pedidos. Sem sessão, o usuário é levado ao
 * login e retorna ao destino original depois de autenticar.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path={paths.dashboard} element={<DashboardPage />} />
        <Route path={paths.login} element={<LoginPage />} />
        <Route path={paths.products} element={<ProductsListPage />} />
        <Route path={`${paths.products}/:id`} element={<ProductDetailPage />} />

        <Route element={<RequireAuth />}>
          <Route
            path={paths.productNew}
            element={<ProductFormPage mode="create" />}
          />
          <Route
            path={`${paths.products}/:id/edit`}
            element={<ProductFormPage mode="edit" />}
          />

          <Route path={paths.profile} element={<ProfilePage />} />

          <Route path={paths.stores} element={<StoresPage />} />
          <Route path={paths.storeNew} element={<StoreFormPage />} />

          <Route path={paths.listings} element={<ListingsPage />} />
          <Route path={paths.orders} element={<OrdersPage />} />
        </Route>

        <Route path="*" element={<Navigate to={paths.dashboard} replace />} />
      </Route>
    </Routes>
  );
}