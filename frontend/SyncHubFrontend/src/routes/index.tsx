import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { RequireAuth } from "../auth/RequireAuth";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { LandingPage } from "../features/auth/LandingPage";
import { LoginPage } from "../features/auth/LoginPage";
import { RegisterPage } from "../features/auth/RegisterPage";
import { ProductsListPage } from "../features/products/ProductsListPage";
import {
  ProductDetailPage,
} from "../features/products/ProductDetailPage";
import { ProductFormPage } from "../features/products/ProductFormPage";
import { ProfilePage } from "../features/profile/ProfilePage";
import { StoresPage } from "../features/stores/StoresPage";
import { StoreFormPage } from "../features/stores/StoreFormPage";
import { ListingsPage } from "../features/listings/ListingsPage";
import { ListingWizardPage } from "../features/listings/ListingWizardPage";
import { OrdersPage } from "../features/orders/OrdersPage";
import { IntegrationsPage } from "../features/integrations/IntegrationsPage";
import { paths } from "./paths";

/**
 * Rotas da aplicação.
 *
 * Liberadas sem sessão (páginas públicas):
 *   /            landing com apresentação da solução (hero, sobre, FAQ, suporte)
 *   /login       página de login (formulário de autenticação)
 *   /register    página de cadastro (formulário de criação de conta)
 *
 * Protegidas por <RequireAuth>: dashboard, catálogo, produtos, perfil, lojas,
 * anúncios, pedidos, integrações e tudo que cria ou edita dados. Sem sessão, o
 * usuário é levado ao login (/login) e retorna ao destino original depois de
 * autenticar.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route path={paths.landing} element={<LandingPage />} />
      <Route path={paths.login} element={<LoginPage />} />
      <Route path={paths.register} element={<RegisterPage />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route path={paths.dashboard} element={<DashboardPage />} />
          <Route path={paths.products} element={<ProductsListPage />} />
          <Route path={`${paths.products}/:id`} element={<ProductDetailPage />} />

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

          <Route path={paths.integrations} element={<IntegrationsPage />} />

          <Route path={paths.listings} element={<ListingsPage />} />
          <Route path={paths.listingNew} element={<ListingWizardPage />} />
          <Route path={paths.orders} element={<OrdersPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to={paths.landing} replace />} />
    </Routes>
  );
}
