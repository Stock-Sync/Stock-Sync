import { Link } from "react-router-dom";
import { GlobalSearch } from "./GlobalSearch";
import { UserMenu } from "./UserMenu";

/**
 * Barra superior: logotipo "SH" à esquerda, busca global e menu do usuário à
 * direita (Imagem 1).
 */
export function Topbar() {
  return (
    <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center gap-4 border-b border-line bg-surface px-4 md:px-6">
      <Link
        to="/"
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-700 text-sm font-extrabold text-white"
        aria-label="StockSync — início"
      >
        SH
      </Link>

      <GlobalSearch />

      <div className="ml-auto flex items-center gap-2">
        <UserMenu />
      </div>
    </header>
  );
}