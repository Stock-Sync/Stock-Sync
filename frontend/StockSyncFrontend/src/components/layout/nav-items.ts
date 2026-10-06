import type { LucideIcon } from "lucide-react";
import { Hexagon, House, LayoutDashboard, Megaphone } from "lucide-react";
import { paths } from "../../routes/paths";

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
}

/**
 * Itens da navegação lateral.
 *
 * O quinto ícone que aparece abaixo da corneta na versão em estudo do design
 * não foi incluído de propósito — a functionality dele ainda não foi definida.
 */
export const navItems: NavItem[] = [
  { label: "Início", to: paths.dashboard, icon: LayoutDashboard },
  { label: "Produtos", to: paths.products, icon: Hexagon },
  { label: "Lojas", to: paths.stores, icon: House },
  { label: "Anúncios", to: paths.listings, icon: Megaphone },
];