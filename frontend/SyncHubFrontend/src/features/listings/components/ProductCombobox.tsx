import {
  type ChangeEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Search } from "lucide-react";
import { controlClasses, invalidControlClasses } from "../../../components/ui/control-styles";
import { Label } from "../../../components/ui/Input";
import { cn } from "../../../lib/cn";
import { useProductViews } from "../../products/queries";

export interface ProductOption {
  id: number;
  skuId: number;
  sku: string;
  title: string;
  price: number;
  stockQuantity: number;
  description: string;
}

export interface ProductComboboxProps {
  value: ProductOption | null;
  onChange: (option: ProductOption | null) => void;
  placeholder?: string;
  disabled?: boolean;
  readOnly?: boolean;
  error?: string;
  label?: string;
  required?: boolean;
}

/**
 * Select pesquisável de produtos do catálogo interno (/products).
 *
 * Busca por nome ou SKU e exibe prévia (SKU, estoque e preço) de cada opção.
 * Ao selecionar, o produto é devolvido via `onChange` para que o formulário
 * padre pré-popule título, preço, estoque e descrição base.
 */
export function ProductCombobox({
  value,
  onChange,
  placeholder = "Buscar produto por nome ou SKU",
  disabled = false,
  readOnly = false,
  error,
  label = "Produto base",
  required = true,
}: ProductComboboxProps) {
  const { products } = useProductViews();
  const [term, setTerm] = useState("");
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  const listboxRef = useRef<HTMLUListElement>(null);

  const options = useMemo(() => {
    const needle = term.trim().toLowerCase();
    return products
      .filter(
        (product) =>
          needle.length === 0 ||
          product.title.toLowerCase().includes(needle) ||
          product.sku.toLowerCase().includes(needle)
      )
      .slice(0, 10)
      .map((product): ProductOption => ({
        id: product.id,
        skuId: product.skuId,
        sku: product.sku,
        title: product.title,
        price: product.price,
        stockQuantity: product.stockQuantity,
        description: product.description,
      }));
  }, [products, term]);

  const select = useCallback(
    (option: ProductOption | null) => {
      setTerm(option ? option.title : "");
      setOpen(false);
      setHighlighted(-1);
      onChange(option);
    },
    [onChange]
  );

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setTerm(value);
    if (!open) {
      setOpen(true);
    }
    setHighlighted(-1);
  };

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (!open) {
        if (event.key === "ArrowDown" || event.key === "Enter") {
          event.preventDefault();
          setOpen(true);
          setHighlighted(0);
        }
        return;
      }

      if (event.key === "Escape") {
        setOpen(false);
        setHighlighted(-1);
        return;
      }

      if (event.key === "ArrowDown") {
        event.preventDefault();
        setHighlighted((prev) => Math.min(prev + 1, options.length - 1));
        return;
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        setHighlighted((prev) => Math.max(prev - 1, 0));
        return;
      }

      if (event.key === "Enter") {
        event.preventDefault();
        const active = options[highlighted];
        if (active) {
          select(active);
        }
      }
    },
    [open, options, highlighted, select]
  );

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        listboxRef.current &&
        !listboxRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
        setHighlighted(-1);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const fieldId = "product-combobox";
  const displayValue = value?.title ?? "";

  return (
    <div className="space-y-2">
      <Label label={label} htmlFor={fieldId} />
      <div className="relative">
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-slate-400"
        />
        <input
          id={fieldId}
          role="combobox"
          aria-expanded={open}
          aria-controls={open ? `${fieldId}-listbox` : undefined}
          aria-activedescendant={
            open && highlighted >= 0 ? `${fieldId}-option-${highlighted}` : undefined
          }
          aria-invalid={error ? true : undefined}
          aria-required={required || undefined}
          value={value ? displayValue : term}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (!readOnly && !value) {
              setOpen(true);
            }
          }}
          onBlur={() => {
            // Fecha o dropdown um pouco depois para não atrapalhar o clique na opção.
            setTimeout(() => setOpen(false), 150);
          }}
          disabled={disabled || readOnly}
          readOnly={readOnly || Boolean(value)}
          placeholder={placeholder}
          className={cn(
            controlClasses,
            "pl-9",
            error && invalidControlClasses,
            (disabled || readOnly) && "cursor-not-allowed opacity-60"
          )}
        />
        {/* O ícone de chevron/limpar é renderizado pelo componente pai (ListingWizardPage) para evitar sobreposição */}
      </div>

      {error && (
        <p id={`${fieldId}-error`} role="alert" className="mt-1.5 text-xs font-medium text-red-600">
          {error}
        </p>
      )}

      {open && (
        <ul
          ref={listboxRef}
          id={`${fieldId}-listbox`}
          role="listbox"
          aria-label="Produtos disponíveis"
          className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-xl border border-line bg-surface shadow-pop ring-1 ring-black/5"
        >
          {term.trim().length > 0 && options.length === 0 && (
            <li role="none" className="px-3 py-2 text-sm text-slate-500">
              Nenhum produto encontrado para "{term}".
            </li>
          )}
          {options.map((option, index) => {
            const active = index === highlighted;
            return (
              <li
                key={option.skuId}
                role="none"
              >
                <button
                  role="option"
                  id={`${fieldId}-option-${index}`}
                  aria-selected={active}
                  type="button"
                  onClick={() => select(option)}
                  onMouseMove={() => setHighlighted(index)}
                  className={cn(
                    "w-full flex flex-col gap-1 px-3 py-2.5 text-left transition-colors",
                    active ? "bg-brand-50 text-brand-700" : "text-slate-700 hover:bg-slate-100"
                  )}
                >
                  <div className="font-medium">{option.title}</div>
                  <div className="text-xs text-slate-500">
                    <span className="font-mono">{option.sku}</span>
                    <span className="mr-1">•</span>
                    Estoque <span className="font-semibold">{option.stockQuantity}</span>
                    <span className="mr-1">•</span>
                    Preço <span className="font-semibold">{option.price.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}</span>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {value && (
        <div className="flex items-center gap-2 rounded-xl border border-line bg-slate-50/50 px-3 py-2">
          <span className="font-mono text-xs font-semibold text-slate-600">
            {value.sku}
          </span>
          <span className="text-xs text-slate-500">
            {value.stockQuantity} un. •{" "}
            {value.price.toLocaleString("pt-BR", {
              style: "currency",
              currency: "BRL",
            })}
          </span>
          <span className="text-xs text-slate-500">pronto para anunciar</span>
        </div>
      )}
    </div>
  );
}
