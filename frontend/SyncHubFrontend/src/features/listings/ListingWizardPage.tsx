import {
  createContext,
  type Dispatch,
  type SetStateAction,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ChevronRight,
  Megaphone,
  Plus,
  X,
  ChevronDown,
  AlertTriangle,
} from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Card, CardBody, CardFooter } from "../../components/ui/Card";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { Textarea } from "../../components/ui/Textarea";
import { Badge } from "../../components/ui/Badge";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingBlock, Spinner } from "../../components/ui/Spinner";
import { PageHeader } from "../../components/ui/PageHeader";
import { useToast } from "../../components/ui/toast-context";
import { PhotoGallery } from "./components/PhotoGallery";
import {
  ProductCombobox,
  type ProductOption,
} from "./components/ProductCombobox";
import { catalogClient } from "../../lib/api/catalog-client";
import { integrationsClient } from "../../lib/api/integrations-client";
import { mercadolibreClient } from "../../lib/api/mercadolibre-client";
import {
  useCategoryAttributes,
  useCategoryDetail,
  useCreateMlItem,
  useCreateMlItemDescription,
  useCreatePlatformMapping,
  useSiteCategories,
  useUpdateMlItem,
} from "./queries";
import { cn } from "../../lib/cn";
import { parseDecimal, formatCurrency } from "../../lib/format";
import { paths } from "../../routes/paths";
import { ApiError } from "../../types/api";
import type {
  MlCategoryAttribute,
  MlCategoryDetail,
  MlItemResponse,
  UpdateMlItemRequest,
} from "../../lib/api/mercadolibre-client";

type WizardStep = 1 | 2 | 3 | 4 | 5;

type ListingType = "gold_pro" | "gold_special";
type ListingCondition = "new" | "used";

interface FormAttribute {
  id: string;
  name: string;
  type: string;
  value_type: string;
  required: boolean;
  allowed_values?: Array<{ id: string; name: string }>;
  tags?: Record<string, unknown>;
  max_length?: number;
  value_name: string;
  value_id?: string;
}

interface WizardData {
  product: ProductOption | null;
  category: { category_id: string; category_name: string } | null;
  title: string;
  listingTypeId: ListingType;
  condition: ListingCondition;
  price: string;
  quantity: string;
  description: string;
  pictures: Array<{ source: string }>;
  attributes: FormAttribute[];
}

const INITIAL_DATA: WizardData = {
  product: null,
  category: null,
  title: "",
  listingTypeId: "gold_special",
  condition: "new",
  price: "",
  quantity: "",
  description: "",
  pictures: [],
  attributes: [],
};

const LISTING_TYPES: Array<{ value: ListingType; label: string }> = [
  { value: "gold_special", label: "Clássico (gold_special)" },
  { value: "gold_pro", label: "Premium (gold_pro)" },
];

const LISTING_CONDITIONS: Array<{ value: ListingCondition; label: string }> = [
  { value: "new", label: "Novo" },
  { value: "used", label: "Usado" },
];

/** Rótulo do botão de avançar em cada passo do assistente. */
const NEXT_LABELS: Record<WizardStep, string> = {
  1: "Próximo: categoria do anúncio",
  2: "Próximo: dados do anúncio",
  3: "Próximo: atributos técnicos",
  4: "Próximo: revisão",
  5: "",
};

/** Lista estável usada quando a query de atributos ainda não resolveu. */
const EMPTY_CATEGORY_ATTRIBUTES: MlCategoryAttribute[] = [];

function isRequiredAttribute(attr: MlCategoryAttribute): boolean {
  if (attr.required) {
    return true;
  }
  const tags = attr.tags;
  if (!tags) {
    return false;
  }
  if (Array.isArray(tags)) {
    return tags.includes("required") || tags.includes("catalog_required");
  }
  return tags.required === true || tags.catalog_required === true;
}

function toFormAttribute(attr: MlCategoryAttribute): FormAttribute {
  return {
    id: attr.id,
    name: attr.name,
    type: attr.type,
    value_type: attr.value_type,
    required: isRequiredAttribute(attr),
    allowed_values: attr.allowed_values,
    tags: attr.tags,
    max_length: attr.max_length,
    value_name: "",
    value_id: undefined,
  };
}

interface WizardContextValue {
  step: WizardStep;
  setStep: (step: WizardStep) => void;
  data: WizardData;
  setData: (updater: (prev: WizardData) => WizardData) => void;
  setField: <K extends keyof WizardData>(key: K, value: WizardData[K]) => void;
  errors: Record<string, string>;
  setErrors: (errors: Record<string, string>) => void;
  formError: string;
  setFormError: (message: string) => void;
  submitting: boolean;
  setSubmitting: (submitting: boolean) => void;
  setAttributeValue: (id: string, valueName: string, valueId?: string) => void;
  categoryAttributes: MlCategoryAttribute[];
  loadingAttributes: boolean;
  isEdit: boolean;
  // Passo 2: categoria
  treeView: boolean;
  setTreeView: (value: boolean) => void;
  treePath: Array<{ id: string; name: string }>;
  setTreePath: Dispatch<SetStateAction<Array<{ id: string; name: string }>>>;
  expandedNode: { id: string; name: string } | null;
  setExpandedNode: (node: { id: string; name: string } | null) => void;
  siteCategories: Array<{ id: string; name: string }>;
  categoryDetail: MlCategoryDetail | undefined;
  categoryDetailLoading: boolean;
  // Passo 2: categoria
  hasMlCredential: boolean;
  // Handlers
  handleNext: () => void;
  handleBack: () => void;
  handlePublish: () => Promise<void>;
  // Edição
  mlItemId: string | null;
  setMlItemId: (id: string | null) => void;
}

const WizardContext = createContext<WizardContextValue | null>(null);

function useWizard(): WizardContextValue {
  const context = useContext(WizardContext);
  if (!context) {
    throw new Error(
      "useWizard precisa ser usado dentro de <WizardContext.Provider>."
    );
  }
  return context;
}

// ---------------------------------------------------------------------------
// Passo 1: Seleção do produto base
// ---------------------------------------------------------------------------
function ProductSelectionStep() {
  const { data, setData, errors, setErrors, setFormError, setStep, isEdit } =
    useWizard();

  const handleProductChange = (option: ProductOption | null) => {
    if (!option) {
      setData((prev) => ({
        ...prev,
        product: null,
        title: "",
        price: "",
        quantity: "",
        description: "",
        pictures: [],
      }));
      setErrors({});
      return;
    }
    setData((prev) => ({
      ...prev,
      product: option,
      title: option.title.slice(0, 60),
      price: String(option.price),
      quantity: String(option.stockQuantity),
      description: option.description,
      pictures: [],
    }));
    setErrors({});
    setFormError("");
    // Avança automaticamente: produto selecionado valida o passo 1.
    if (!isEdit) {
      setStep(2);
    }
  };

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-bold text-slate-900">
          Passo 1 de 5 — Seleção do produto base
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Escolha o produto do catálogo interno que será anunciado. Título,
          preço, estoque e descrição base são pré-preenchidos a partir do
          produto selecionado.
        </p>
      </div>

      <Card>
        <CardBody className="p-5">
          <div className="relative">
            <ProductCombobox
              value={data.product}
              onChange={handleProductChange}
              placeholder="Buscar produto por nome ou SKU"
              disabled={isEdit}
              readOnly={isEdit && Boolean(data.product)}
              error={errors.product}
            />
            {/* Renderização condicional limpa para evitar sobreposição de ícones (X vs Seta) */}
            <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none flex items-center text-slate-400">
              {data.product ? (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (!isEdit) {
                      handleProductChange(null);
                    }
                  }}
                  className={cn(
                    "pointer-events-auto hover:text-slate-600 transition-colors",
                    isEdit && "opacity-50 cursor-not-allowed"
                  )}
                  title="Limpar seleção"
                >
                  <X className="h-4 w-4" />
                </button>
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </div>
          </div>
          {isEdit && data.product && (
            <p className="mt-2 text-xs text-slate-500">
              Edição: produto vinculado mantido (não é possível trocar o produto
              de um anúncio existente).
            </p>
          )}
        </CardBody>
      </Card>

      {data.product && (
        <Card className="mt-4">
          <CardBody className="p-4">
            <h3 className="text-sm font-semibold text-slate-800 mb-3">
              Pré-preenchimento do formulário
            </h3>
            <dl className="grid gap-2 sm:grid-cols-2 text-sm">
              <dt className="font-medium text-slate-600">Produto</dt>
              <dd className="font-medium text-slate-900">{data.title}</dd>
              <dt className="font-medium text-slate-600">SKU</dt>
              <dd className="font-mono text-slate-700">{data.product.sku}</dd>
              <dt className="font-medium text-slate-600">Estoque</dt>
              <dd className="text-slate-700">
                {data.product.stockQuantity} un.
              </dd>
              <dt className="font-medium text-slate-600">Preço base</dt>
              <dd className="font-semibold text-slate-900">
                {formatCurrency(data.product.price)}
              </dd>
            </dl>
            <p className="mt-3 text-xs text-slate-500">
              Esses valores podem ser ajustados nos próximos passos.
            </p>
          </CardBody>
        </Card>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Passo 2: Categoria (Domain Discovery + árvore de fallback)
// ---------------------------------------------------------------------------
function CategoryStep() {
  const {
    data,
    setData,
    setErrors,
    setFormError,
    setStep,
    isEdit,
    treeView,
    setTreeView,
    treePath,
    setTreePath,
    expandedNode,
    setExpandedNode,
    siteCategories,
    categoryDetail,
    categoryDetailLoading,
    hasMlCredential,
  } = useWizard();

  const isLeafLevel =
    expandedNode && categoryDetail
      ? (categoryDetail.children_categories ?? []).length === 0
      : false;

  const currentLevel = useMemo(() => {
    if (!expandedNode) {
      return siteCategories;
    }
    if (categoryDetailLoading) {
      return [];
    }
    if (isLeafLevel) {
      return [expandedNode];
    }
    return categoryDetail?.children_categories ?? [];
  }, [
    expandedNode,
    siteCategories,
    categoryDetail,
    categoryDetailLoading,
    isLeafLevel,
  ]);

  const goUpLevel = () => {
    if (treePath.length === 0) {
      setExpandedNode(null);
      return;
    }
    const rest = treePath.slice(0, -1);
    setTreePath(rest);
    setExpandedNode(rest.length > 0 ? rest[rest.length - 1] : null);
  };

  const drillNode = (node: { id: string; name: string }) => {
    setTreePath([...treePath, node]);
    setExpandedNode(node);
  };

  const selectTreeCategory = (node: { id: string; name: string }) => {
    setData((prev) => ({
      ...prev,
      category: { category_id: node.id, category_name: node.name },
    }));
    setTreePath([]);
    setExpandedNode(null);
    setTreeView(false);
    setErrors({});
    setFormError("");
    setStep(3);
  };

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-bold text-slate-900">
          Passo 2 de 5 — Categoria do anúncio
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          A categoria deve ser um nó folha (sem subcategorias). Use a navegação
          em árvore abaixo para selecioná-la.
        </p>
      </div>

      {!isEdit && data.product && (
        <Card className="mb-6">
          <CardBody className="p-4">
            <h3 className="text-sm font-semibold text-slate-800 mb-3">
              Produto selecionado
            </h3>
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm font-medium text-slate-900">
                {data.product.title}
              </span>
              <span className="font-mono text-xs text-slate-600">
                {data.product.sku}
              </span>
              <span className="text-xs text-slate-500">
                Estoque {data.product.stockQuantity} un. •{" "}
                {formatCurrency(data.product.price)}
              </span>
            </div>
          </CardBody>
        </Card>
      )}

      {!isEdit && hasMlCredential === false && (
        <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 mb-6">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <h3 className="text-sm font-semibold text-amber-800">
                Mercado Livre não conectado
              </h3>
              <p className="text-sm text-amber-700">
                Você precisa conectar sua conta do Mercado Livre antes de criar
                um anúncio. Acesse a página de
                <Link to={paths.integrations} className="text-amber-700 hover:underline">
                  Integrações
                </Link>
                para conectar sua conta.
              </p>
            </div>
          </div>
        </div>
      )}
      {!isEdit && data.category === null && (
        <Card className="border-brand-50 bg-brand-50/50">
          <CardBody className="p-4">
            <div className="flex items-start gap-3">
              <Megaphone className="h-5 w-5 text-brand-700 shrink-0 mt-0.5" />
              <div>
                <h3 className="text-sm font-semibold text-brand-800">
                  Edição — categoria mantida
                </h3>
                <p className="text-sm text-brand-700">
                  A categoria do anúncio original é preservada. Não é possível
                  alterar a categoria de um anúncio já publicado neste fluxo.
                </p>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      {!isEdit && (
        <>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => setTreeView(true)}
            className="w-full text-xs text-brand-700 mb-3"
          >
            <Plus className="h-3 w-3 mr-1" />
            Navegar pela árvore de categorias
          </Button>
          {treeView && (
            <Card className="max-w-md mx-auto">
              <CardBody className="p-5">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xs font-semibold text-slate-600">
                    Caminho:
                  </span>
                  {treePath.map((node, i) => (
                    <span
                      key={i}
                      className={cn(
                        "text-xs truncate",
                        i < treePath.length - 1
                          ? "text-slate-500"
                          : "text-brand-700 font-medium"
                      )}
                    >
                      {i > 0 && " › "}
                      {node.name}
                    </span>
                  ))}
                </div>

                {categoryDetailLoading && (
                  <div className="flex items-center gap-2 text-xs text-slate-500 py-2">
                    <Spinner className="h-3 w-3" />
                    <span>Carregando subcategorias…</span>
                  </div>
                )}
                {!categoryDetailLoading && (
                  <p className="text-xs text-slate-500 mb-2">
                    Navegue até uma categoria folha (sem subcategorias) e clique
                    em <strong>Selecionar</strong>.
                  </p>
                )}
                <div className="space-y-2">
                  {currentLevel.map((node) => (
                    <button
                      key={node.id}
                      type="button"
                      onClick={() =>
                        isLeafLevel ? selectTreeCategory(node) : drillNode(node)
                      }
                      className="w-full flex justify-between items-center px-3 py-2.5 rounded-lg border border-line text-left text-sm transition-colors hover:bg-slate-50"
                    >
                      <span className="text-slate-700">{node.name}</span>
                      {isLeafLevel ? (
                        <span className="text-xs text-brand-700">
                          Selecionar
                        </span>
                      ) : (
                        <ChevronRight className="h-3 w-3 text-slate-400" />
                      )}
                    </button>
                  ))}
                </div>

                {treePath.length > 0 && (
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={goUpLevel}
                  >
                    <ArrowLeft className="h-3 w-3 mr-1" /> Voltar um nível
                  </Button>
                )}
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setTreeView(false)}
                >
                  Fechar
                </Button>
              </CardBody>
            </Card>
          )}
        </>
      )}

      {data.category && (
        <div className="flex items-center gap-2 rounded-xl border border-line bg-slate-50/50 px-3 py-2">
          <Badge>Categoria: {data.category.category_name}</Badge>
          <span className="text-xs text-slate-500 font-mono">
            {data.category.category_id}
          </span>
          {!isEdit && (
            <button
              type="button"
              onClick={() => setData((prev) => ({ ...prev, category: null }))}
              className="text-xs text-slate-400 hover:text-red-600 underline"
            >
              Alterar
            </button>
          )}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Controle de um único atributo técnico
// ---------------------------------------------------------------------------
function AttributeControl({ attr }: { attr: FormAttribute }) {
  const { errors, setAttributeValue } = useWizard();
  const fieldId = `attr-${attr.id}`;
  const hasError = Boolean(errors[`attr-${attr.id}`]);
  const labelRequired = attr.required ? " (obrigatório)" : "";
  const [unit, setUnit] = useState<string>("");

  if (attr.allowed_values?.length) {
    const allowed = attr.allowed_values ?? [];
    return (
      <div key={fieldId} className="space-y-1">
        <label className="mb-1 block text-sm font-medium text-slate-700">
          {attr.name}
          {labelRequired}
        </label>
        <select
          id={fieldId}
          value={attr.value_id ?? ""}
          onChange={(event) => {
            const chosen = allowed.find((v) => v.id === event.target.value);
            setAttributeValue(
              attr.id,
              chosen?.name ?? event.target.value,
              chosen?.id ?? undefined
            );
          }}
          className={cn(
            "block w-full rounded-xl border border-line bg-surface p-2.5 text-slate-700 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none",
            hasError && "border-red-500 ring-1 ring-red-500"
          )}
        >
          <option value="">Selecione uma opção</option>
          {allowed.map((option) => (
            <option key={option.id} value={option.id}>
              {option.name}
            </option>
          ))}
        </select>
        {hasError && (
          <p className="mt-1 text-xs text-red-600">
            {errors[`attr-${attr.id}`]}
          </p>
        )}
      </div>
    );
  }

  if (attr.value_type === "boolean") {
    return (
      <div key={fieldId} className="space-y-2">
        <label className="mb-1 block text-sm font-medium text-slate-700">
          {attr.name}
          {labelRequired}
        </label>
        <div className="flex items-center gap-3">
          {["Sim", "Não"].map((label) => (
            <label
              key={label}
              className="flex items-center gap-2 text-sm cursor-pointer"
            >
              <input
                type="radio"
                name={fieldId}
                value={label}
                checked={attr.value_name === label}
                onChange={(event) =>
                  setAttributeValue(attr.id, event.target.value)
                }
                className="form-radio h-4 w-4 text-brand-600 border-slate-300"
              />
              {label}
            </label>
          ))}
          {hasError && (
            <p className="mt-1 text-xs text-red-600">
              {errors[`attr-${attr.id}`]}
            </p>
          )}
        </div>
      </div>
    );
  }

  if (attr.type === "number" || attr.value_type === "number") {
    const numericPart = attr.value_name.replace(/[^0-9,.-].*$/s, "").trim();
    const combine = (number: string, unitText: string) =>
      `${number}${unitText ? " " + unitText : ""}`;

    return (
      <div key={fieldId} className="space-y-1">
        <label className="mb-1 block text-sm font-medium text-slate-700">
          {attr.name}
          {labelRequired}
        </label>
        <div className="flex gap-2 items-end">
          <Input
            id={fieldId}
            label=""
            type="number"
            value={numericPart}
            onChange={(event) =>
              setAttributeValue(attr.id, combine(event.target.value, unit))
            }
            placeholder="0"
            error={hasError ? errors[`attr-${attr.id}`] : undefined}
            className="flex-1"
          />
          <Input
            id={`${fieldId}-unit`}
            label=""
            placeholder="Unidade"
            value={unit}
            onChange={(event) => {
              setUnit(event.target.value);
              setAttributeValue(
                attr.id,
                combine(numericPart, event.target.value)
              );
            }}
            error={hasError ? errors[`attr-${attr.id}`] : undefined}
            className="w-24"
          />
        </div>
        {hasError && (
          <p className="mt-1 text-xs text-red-600">
            {errors[`attr-${attr.id}`]}
          </p>
        )}
      </div>
    );
  }

  return (
    <div key={fieldId} className="space-y-1">
      <label className="mb-1 block text-sm font-medium text-slate-700">
        {attr.name}
        {labelRequired}
      </label>
      <Input
        id={fieldId}
        label=""
        value={attr.value_name}
        onChange={(event) => setAttributeValue(attr.id, event.target.value)}
        placeholder={
          attr.max_length ? `Máx. ${attr.max_length} caracteres` : undefined
        }
        error={hasError ? errors[`attr-${attr.id}`] : undefined}
        maxLength={attr.max_length}
        required={attr.required}
      />
      {hasError && (
        <p className="mt-1 text-xs text-red-600">{errors[`attr-${attr.id}`]}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Passo 3: Dados do anúncio e descrição
// ---------------------------------------------------------------------------
function ListingDataStep() {
  const { data, setField, errors, isEdit } = useWizard();

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-bold text-slate-900">
          Passo 3 de 5 — Dados do anúncio
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Configure o anúncio que será publicado no Mercado Livre.
        </p>
      </div>

      {data.category && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-slate-50/50 px-3 py-2">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Categoria
          </span>
          <span className="text-sm font-medium text-slate-900">
            {data.category.category_name}
          </span>
          <span className="font-mono text-xs text-slate-500">
            {data.category.category_id}
          </span>
        </div>
      )}

      <Card>
        <CardBody className="p-5">
          <div className="space-y-4">
            <Input
              label="Título do anúncio"
              value={data.title}
              onChange={(event) => setField("title", event.target.value)}
              maxLength={60}
              error={errors.title}
              required
            />
            <div className="flex justify-end">
              <span className="text-xs text-slate-400">
                {data.title.length}/60 caracteres
              </span>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Select
                label="Tipo de anúncio"
                value={data.listingTypeId}
                onChange={(event) =>
                  setField("listingTypeId", event.target.value as ListingType)
                }
                options={LISTING_TYPES}
                error={errors.listingType}
                required
              />
              <Select
                label="Condição"
                value={data.condition}
                onChange={(event) =>
                  setField("condition", event.target.value as ListingCondition)
                }
                options={LISTING_CONDITIONS}
                error={errors.condition}
                required
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Input
                label="Preço de venda (R$)"
                inputMode="decimal"
                value={data.price}
                onChange={(event) => setField("price", event.target.value)}
                placeholder="0,00"
                error={errors.price}
                required
              />
              <Input
                label="Quantidade disponível"
                inputMode="numeric"
                value={data.quantity}
                onChange={(event) => setField("quantity", event.target.value)}
                placeholder="1"
                error={errors.quantity}
                required
              />
            </div>

            {/* Galeria limpa de artefatos visuais / riscos */}
            <div className="rounded-xl border border-slate-200 p-4 bg-white">
              <PhotoGallery
                value={data.pictures}
                onChange={(pictures) => setField("pictures", pictures)}
              />
            </div>
            {errors.pictures && (
              <p role="alert" className="text-xs font-medium text-red-600">
                {errors.pictures}
              </p>
            )}

            <Textarea
              label="Descrição do anúncio"
              value={data.description}
              onChange={(event) => setField("description", event.target.value)}
              placeholder={
                isEdit
                  ? "Deixe em branco para manter a descrição atual do anúncio"
                  : "Descrição do produto para publicação"
              }
              rows={4}
              required={!isEdit}
              error={errors.description}
            />
            <p className="text-xs text-slate-500">
              {isEdit
                ? "Se preenchida, a descrição será reenviada ao Mercado Livre."
                : "Pré-preenchida com a descrição base do produto; revise antes de publicar."}
            </p>
          </div>
        </CardBody>
      </Card>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Passo 4: Atributos técnicos
// ---------------------------------------------------------------------------
function AttributesStep() {
  const { data, errors, categoryAttributes, loadingAttributes } = useWizard();

  const mandatory = data.attributes.filter((attr) => attr.required);
  const optional = data.attributes.filter((attr) => !attr.required);

  // Scroll to top when entering this step or when attributes load/change
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [categoryAttributes, loadingAttributes]);

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-bold text-slate-900">
          Passo 4 de 5 — Atributos técnicos
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Preencha os atributos exigidos pela categoria{" "}
          <strong>{data.category?.category_name}</strong>. Atributos com{" "}
          <em>allowed_values</em> usam lista de opções; booleanos usam sim/não;
          numéricos usam campo numérico.
        </p>
      </div>

      {loadingAttributes && <LoadingBlock label="Carregando atributos..." />}

      {data.category && categoryAttributes.length > 0 ? (
        <>
          <Card>
            <CardBody className="p-5">
              <h3 className="text-sm font-semibold text-slate-800 mb-3">
                Obrigatórios
              </h3>
              <div className="space-y-3">
                {mandatory.length > 0 ? (
                  <div className="space-y-3">
                    {mandatory.map((attr) => (
                      <div
                        key={attr.id}
                        className="bg-amber-50/50 p-3 rounded-lg border border-amber-100"
                      >
                        <AttributeControl attr={attr} />
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">
                    Nenhum atributo obrigatório para esta categoria.
                  </p>
                )}
              </div>
            </CardBody>
          </Card>

          {optional.length > 0 && (
            <Card>
              <CardBody className="p-5">
                <h3 className="text-sm font-semibold text-slate-800 mb-3">
                  Opcionais e recomendados
                </h3>
                <div className="space-y-3">
                  {optional.map((attr) => (
                    <AttributeControl key={attr.id} attr={attr} />
                  ))}
                </div>
              </CardBody>
            </Card>
          )}
        </>
      ) : null}
      {data.category && categoryAttributes.length === 0 && (
        <EmptyState
          title="Nenhum atributo técnico"
          description="Esta categoria não exige atributos adicionais."
        />
      )}

      {Object.keys(errors).some((key) => key.startsWith("attr-")) && (
        <div className="rounded-xl bg-red-50 p-3 text-sm text-red-700">
          Preencha os atributos obrigatórios antes de avançar.
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Passo 5: Revisão e publicação
// ---------------------------------------------------------------------------
function ReviewStep() {
  const { data, isEdit } = useWizard();

  const attributesWithValues = data.attributes.filter(
    (a) => a.value_name.trim().length > 0
  );

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-bold text-slate-900">
          Passo 5 de 5 — {isEdit ? "Revisão e salvamento" : "Publicação"}
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Confira os dados antes de enviar ao Mercado Livre.
        </p>
      </div>

      <Card>
        <CardBody className="p-5">
          <dl className="grid gap-3 sm:grid-cols-2">
            <dt className="font-medium text-slate-600">Produto base</dt>
            <dd className="text-slate-900">
              {data.product?.title} ({data.product?.sku})
            </dd>
            <dt className="font-medium text-slate-600">Categoria</dt>
            <dd className="text-slate-900 font-mono text-sm">
              {data.category?.category_name} ({data.category?.category_id})
            </dd>
            <dt className="font-medium text-slate-600">Título do anúncio</dt>
            <dd className="text-slate-900">{data.title}</dd>
            <dt className="font-medium text-slate-600">Tipo de anúncio</dt>
            <dd className="text-slate-900">
              {LISTING_TYPES.find((t) => t.value === data.listingTypeId)?.label}
            </dd>
            <dt className="font-medium text-slate-600">Condição</dt>
            <dd className="text-slate-900">
              {
                LISTING_CONDITIONS.find((c) => c.value === data.condition)
                  ?.label
              }
            </dd>
            <dt className="font-medium text-slate-600">Preço de venda</dt>
            <dd className="font-semibold text-slate-900">
              {formatCurrency(parseDecimal(data.price) || 0)}
            </dd>
            <dt className="font-medium text-slate-600">Quantidade</dt>
            <dd className="text-slate-900">{data.quantity} un.</dd>
            <dt className="font-medium text-slate-600">Fotos</dt>
            <dd className="text-slate-900">{data.pictures.length} foto(s)</dd>
            <dt className="font-medium text-slate-600">
              Atributos preenchidos
            </dt>
            <dd className="text-slate-900">
              {attributesWithValues.length} de {data.attributes.length}
            </dd>
          </dl>

          {data.description.trim() && (
            <div className="mt-4 pt-4 border-t border-line">
              <h3 className="text-sm font-semibold text-slate-800 mb-2">
                Descrição
              </h3>
              <p className="text-sm text-slate-600 whitespace-pre-wrap max-h-48 overflow-y-auto">
                {data.description}
              </p>
            </div>
          )}
        </CardBody>
      </Card>

      <div className="rounded-xl bg-amber-50 p-3 text-sm text-amber-700">
        {isEdit
          ? "As alterações serão enviadas ao Mercado Livre (PUT /items) e a descrição será atualizada se preenchida."
          : "Ao confirmar, o anúncio será criado no Mercado Livre (POST /items), a descrição será enviada (POST /items/{id}/description) e o vínculo será salvo no catálogo local."}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Página do assistente
// ---------------------------------------------------------------------------
export function ListingWizardPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { notify } = useToast();

  const editingListingId = searchParams.get("listingId") || undefined;
  const isEdit = Boolean(editingListingId);

  const [step, setStep] = useState<WizardStep>(1);
  const [data, setData] = useState<WizardData>(INITIAL_DATA);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [treeView, setTreeView] = useState(false);
  const [treePath, setTreePath] = useState<Array<{ id: string; name: string }>>(
    []
  );
  const [expandedNode, setExpandedNode] = useState<{
    id: string;
    name: string;
  } | null>(null);

  const [hasMlCredential, setHasMlCredential] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    const checkCredential = async () => {
      try {
        const creds = await integrationsClient.listMercadoLivreCredentials();
        if (!cancelled) {
          setHasMlCredential(creds.length > 0);
        }
      } catch {
        if (!cancelled) {
          setHasMlCredential(false);
        }
      }
    };
    checkCredential();
    return () => {
      cancelled = true;
    };
  }, []);

  const categoryId = data.category?.category_id;
  const attributesQuery = useCategoryAttributes(categoryId ?? "");
  const categoryAttributes = attributesQuery.data ?? EMPTY_CATEGORY_ATTRIBUTES;
  const loadingAttributes = attributesQuery.isPending;
  const { data: siteCategories = [] } = useSiteCategories();
  const { data: categoryDetail, isPending: categoryDetailLoading } =
    useCategoryDetail(expandedNode?.id);

  const createMlItem = useCreateMlItem();
  const createMlItemDescription = useCreateMlItemDescription();
  const createPlatformMapping = useCreatePlatformMapping();
  const updateMlItem = useUpdateMlItem();

  const editInitialized = useRef(false);
  const lastCategoryId = useRef<string | null>(null);
  const [mlItemId, setMlItemId] = useState<string | null>(null);
  const [editError, setEditError] = useState("");
  const [mlItemError, setMlItemError] = useState(false);

  const load = async () => {
    setEditError("");
    setMlItemError(false);

    try {
      const mapping = await catalogClient.getPlatformMapping(
        Number(editingListingId!)
      );
      const sku = await catalogClient.getSku(mapping.sku_id);
      const product = await catalogClient.getProduct(sku.product_id);

      let mlItem: MlItemResponse | null = null;
      if (mapping.platform_product_id) {
        try {
          mlItem = await mercadolibreClient.getMlItem(
            mapping.platform_product_id
          );
          setMlItemId(mapping.platform_product_id);
        } catch (exc: any) {
          const mlErrorMessage =
            exc?.message
              ? `Falha ao carregar dados do Mercado Livre: ${exc.message}`
              : "Falha ao carregar dados do Mercado Livre.";
          if (exc?.status === 401 || exc?.code === "unauthorized") {
            setMlItemError(
              true
            ); // handled below with specific message
            setEditError(
              "Sua sessão do Mercado Livre expirou. Renove o token na página de Integrações e tente novamente."
            );
            return;
          }
          setEditError(mlErrorMessage);
          setMlItemError(true);
          return;
        }
      }

      setData({
        product: {
          id: product.id,
          skuId: sku.id,
          sku: sku.internal_sku,
          title: product.name,
          price: sku.price ?? 0,
          stockQuantity: sku.stock_quantity,
          description: product.description ?? "",
        },
        category: null,
        title: mlItem?.title ?? product.name,
        listingTypeId: (mlItem?.listing_type_id ??
          "gold_special") as ListingType,
        condition: (mlItem?.condition ?? "new") as ListingCondition,
        price: String(mlItem?.price ?? sku.price ?? 0),
        quantity: String(mlItem?.available_quantity ?? sku.stock_quantity),
        description: "",
        pictures: mlItem?._cloudinary_urls
          ? mlItem._cloudinary_urls.map((url: string) => ({
              source: url,
              readOnly: false,
            }))
          : mlItem?.pictures
            ? mlItem.pictures.map((p) => ({
                source: p.secure_url ?? "",
                readOnly: true,
              }))
            : mlItem?.thumbnail
              ? [{ source: mlItem.thumbnail, readOnly: true }]
              : [],
        attributes: (mlItem?.attributes ?? []).map((a) => ({
          id: a.id,
          name: a.id,
          type: "string",
          value_type: "string",
          required: false,
          value_name: a.value_name ?? "",
          value_id: a.value_id ?? undefined,
        })),
      });
    } catch {
      setEditError(
        "Não foi possível carregar os dados do anúncio para edição."
      );
    }
  };

  useEffect(() => {
    if (!editingListingId || editInitialized.current) {
      return;
    }

    editInitialized.current = true;
    load();
  }, [editingListingId]);

  useEffect(() => {
    if (!data.category || loadingAttributes) {
      return;
    }
    if (lastCategoryId.current === data.category.category_id) {
      return;
    }
    lastCategoryId.current = data.category.category_id;
    setData((prev) => ({
      ...prev,
      attributes: categoryAttributes.map(toFormAttribute),
    }));
  }, [data.category, categoryAttributes, loadingAttributes]);

  const setField = useCallback(
    <K extends keyof WizardData>(key: K, value: WizardData[K]) => {
      setData((prev) => ({ ...prev, [key]: value }));
    },
    []
  );

  const setAttributeValue = useCallback(
    (id: string, valueName: string, valueId?: string) => {
      setData((prev) => ({
        ...prev,
        attributes: prev.attributes.map((a) =>
          a.id === id ? { ...a, value_name: valueName, value_id: valueId } : a
        ),
      }));
      setErrors((prev) => {
        const next = { ...prev };
        delete next[`attr-${id}`];
        return next;
      });
    },
    []
  );

  const validateStep = useCallback(
    (step: WizardStep): Record<string, string> => {
      const d = data;
      const e: Record<string, string> = {};

      switch (step) {
        case 1:
          if (!d.product) {
            e.product = "Selecione um produto do catálogo interno.";
          }
          return e;
        case 2:
          if (!isEdit && !d.category) {
            e.category = "Selecione uma categoria folha do Mercado Livre.";
          }
          return e;
        case 3: {
          if (!d.title.trim()) {
            e.title = "Informe o título do anúncio.";
          } else if (d.title.length > 60) {
            e.title = "O título deve ter no máximo 60 caracteres.";
          } else if (d.title.trim().length < 10) {
            e.title = "O título é muito curto. Inclua características importantes do produto, como marca, modelo ou categoria (mínimo 10 caracteres).";
          }
          const price = parseDecimal(d.price);
          if (Number.isNaN(price) || price <= 0) {
            e.price = "Informe um preço de venda válido.";
          }
          const qty = parseInt(d.quantity, 10);
          if (!Number.isFinite(qty) || qty < 0) {
            e.quantity = "Informe uma quantidade válida.";
          }
          if (d.pictures.length === 0) {
            e.pictures = "Adicione pelo menos uma foto ao anúncio.";
          }
          if (!isEdit && !d.description.trim()) {
            e.description = "Informe a descrição do anúncio.";
          }
          return e;
        }
        case 4: {
          for (const attr of d.attributes) {
            if (attr.required && !attr.value_name.trim()) {
              e[`attr-${attr.id}`] = `O atributo "${attr.name}" é obrigatório.`;
            }
          }
          return e;
        }
        default:
          return e;
      }
    },
    [data, isEdit]
  );

  const handleNext = useCallback(() => {
    const stepErrors = validateStep(step);
    if (Object.keys(stepErrors).length > 0) {
      setErrors(stepErrors);
      setFormError(
        "Corrija os campos destacados antes de avançar para o próximo passo."
      );
      return;
    }
    setErrors({});
    setFormError("");
    setStep((prev) => (prev + 1) as WizardStep);
  }, [step, validateStep]);

  const handleBack = useCallback(() => {
    setErrors({});
    setFormError("");
    setStep((prev) => (prev - 1) as WizardStep);
  }, []);

  const handleRetry = useCallback(() => {
    setEditError("");
    setMlItemError(false);
    editInitialized.current = false;
    load();
  }, [load]);

  const handlePublish = async () => {
    const stepErrors = validateStep(3);
    const attrErrors = validateStep(4);
    if (
      Object.keys(stepErrors).length > 0 ||
      Object.keys(attrErrors).length > 0
    ) {
      setErrors({ ...stepErrors, ...attrErrors });
      setFormError("Corrija os campos destacados antes de publicar.");
      setStep(3);
      return;
    }

    setFormError("");
    setSubmitting(true);

    const price = parseDecimal(data.price);
    const quantity = parseInt(data.quantity, 10);
    const attributes = data.attributes
      .map((a) => ({
        id: a.id,
        value_name: a.value_name,
        value_id: a.value_id,
      }))
      .filter((a) => a.value_name.trim().length > 0);

    try {
      if (isEdit) {
        if (!mlItemId) {
          throw new Error("Item do Mercado Livre não identificado.");
        }
        // On edit, only send Cloudinary URLs as `source`. Mercado Libre's
        // /items endpoint downloads from `source`; it cannot fetch from its
        // own CDN secure_urls. When no new Cloudinary images were added,
        // omit `pictures` entirely so ML keeps the existing images.
        const cloudinaryPictures = data.pictures.filter((p) =>
          p.source.includes("cloudinary.com")
        );
        const payload: UpdateMlItemRequest = {
          title: data.title,
          price,
          available_quantity: quantity,
          ...(cloudinaryPictures.length > 0
            ? {
                pictures: cloudinaryPictures.map((p) => ({
                  source: p.source,
                })),
              }
            : {}),
          attributes,
        };
        if (data.description.trim()) {
          payload.description = data.description;
        }
        await updateMlItem.mutateAsync({ itemId: mlItemId, payload });
        notify({
          tone: "success",
          title: "Anúncio atualizado",
          description: data.title,
        });
      } else {
        if (!data.product) {
          throw new Error("Produto base não selecionado.");
        }
        const item = await createMlItem.mutateAsync({
          family_name: data.title,
          category_id: data.category!.category_id,
          listing_type_id: data.listingTypeId,
          condition: data.condition,
          currency_id: "BRL",
          buying_mode: "buy_it_now",
          price,
          available_quantity: quantity,
          pictures: data.pictures.map((p) => ({ source: p.source })),
          attributes,
          sku_id: data.product.skuId,
          product_id: data.product.id,
        });

        if (data.description.trim() && item.id) {
          await createMlItemDescription.mutateAsync({
            itemId: item.id,
            plainText: data.description,
          });
        }

        await createPlatformMapping.mutateAsync({
          sku_id: data.product.skuId,
          platform: "mercado_livre",
          platform_sku: data.product.sku,
          platform_product_id: item.id,
          is_active: true,
        });

        notify({
          tone: "success",
          title: "Anúncio publicado",
          description: `${data.title} (${item.id})`,
        });
      }
      navigate(paths.listings);
    } catch (caught) {
      setSubmitting(false);
      let message =
        caught instanceof ApiError
          ? caught.message
          : "Falha ao publicar o anúncio no Mercado Livre.";
      const details = (caught as any)?.details;
      if (details?.ml_error) {
        const err = details.ml_error;
        const msg =
          typeof err === "string"
            ? err
            : err?.message || err?.cause || JSON.stringify(err);
        message = `Falha ao criar item no Mercado Livre: ${msg}`;
      }
      setFormError(message);
      notify({
        tone: "error",
        title: "Falha ao publicar anúncio",
        description: message,
      });
    }
  };

  const ctx: WizardContextValue = {
    step,
    setStep,
    data,
    setData,
    setField,
    setAttributeValue,
    errors,
    setErrors,
    formError,
    setFormError,
    submitting,
    setSubmitting,
    isEdit,
    treeView,
    setTreeView,
    treePath,
    setTreePath,
    expandedNode,
    setExpandedNode,
    categoryAttributes,
    loadingAttributes,
    siteCategories,
    categoryDetail,
    categoryDetailLoading,
    hasMlCredential,
    handleNext,
    handleBack,
    handlePublish,
    mlItemId,
    setMlItemId,
  };

  const stepLabels: Record<WizardStep, string> = {
    1: "Seleção do produto base",
    2: "Categoria do anúncio",
    3: "Dados do anúncio",
    4: "Atributos técnicos",
    5: isEdit ? "Revisão e salvamento" : "Publicação",
  };

  if (editError) {
    return (
      <div className="space-y-6">
        <PageHeader title="Editar anúncio" />
        <EmptyState
          title="Não foi possível carregar o anúncio"
          description={editError}
          action={
            <Link
              to={paths.listings}
              className="text-sm font-semibold text-brand-700 hover:underline"
            >
              Voltar para anúncios
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <WizardContext.Provider value={ctx}>
      <div className="space-y-6">
        <PageHeader
          title={isEdit ? "Editar anúncio" : "Novo anúncio"}
          description={
            isEdit
              ? "Altere os dados do anúncio vinculado ao marketplace."
              : "Crie um anúncio de Mercado Livre a partir de um produto do catálogo interno."
          }
          actions={
            <Link
              to={paths.listings}
              className="inline-flex items-center gap-2 text-sm text-slate-500 hover:underline"
            >
              <ArrowLeft className="h-4 w-4" /> Voltar para anúncios
            </Link>
          }
        />

        <Card>
          <CardBody className="p-0 md:p-0">
            <div className="border-b border-line bg-slate-50 px-6 py-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                    Passo {step} de 5
                  </span>
                </div>
                <div className="flex gap-1">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      type="button"
                      disabled={n > step}
                      onClick={() => {
                        if (n > step) {
                          return;
                        }
                        setErrors({});
                        setFormError("");
                        setStep(n as WizardStep);
                      }}
                      aria-label={`Passo ${n} de 5 — ${stepLabels[n as WizardStep]}`}
                      className={cn(
                        "flex h-8 w-8 items-center justify-center rounded-full text-xs font-medium transition-colors",
                        n < step
                          ? "bg-brand-100 text-brand-700"
                          : n === step
                            ? "bg-brand-700 text-white ring-2 ring-brand-700"
                            : "bg-slate-200 text-slate-400 hover:bg-slate-300"
                      )}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>
              <p className="mt-2 text-xs text-slate-500">{stepLabels[step]}</p>
            </div>

            <div className="p-6 md:p-8">
              {step === 1 && <ProductSelectionStep />}
              {step === 2 && <CategoryStep />}
              {step === 3 && <ListingDataStep />}
              {step === 4 && <AttributesStep />}
              {step === 5 && <ReviewStep />}
            </div>

            <CardFooter className="border-t border-line">
              <div className="flex justify-between items-center w-full">
                {step > 1 ? (
                  <Button
                    variant="secondary"
                    onClick={handleBack}
                    disabled={submitting}
                  >
                    <ArrowLeft className="mr-2 h-4 w-4" /> Voltar
                  </Button>
                ) : (
                  <div />
                )}
                <div className="flex items-center gap-2">
                  {/* Botão Cancelar padronizado com o componente Button e alinhado corretamente */}
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={submitting}
                    onClick={(event) => {
                      if (
                        data.product ||
                        data.category ||
                        data.title ||
                        data.pictures.length > 0
                      ) {
                        if (
                          !window.confirm(
                            "Sair do assistente? Os dados preenchidos serão perdidos."
                          )
                        ) {
                          event.preventDefault();
                          return;
                        }
                      }
                      navigate(paths.listings);
                    }}
                  >
                    Cancelar
                  </Button>

                  {step === 5 ? (
                    <Button
                      onClick={handlePublish}
                      disabled={submitting || mlItemError}
                    >
                      {submitting
                        ? "Processando…"
                        : isEdit
                          ? "Salvar alterações"
                          : "Publicar no Mercado Livre"}
                    </Button>
                  ) : (
                    <Button onClick={handleNext} disabled={submitting}>
                      {NEXT_LABELS[step]}{" "}
                      <ChevronRight className="ml-2 h-4 w-4" />
                    </Button>
                  )}
                </div>
              </div>
            </CardFooter>
          </CardBody>
        </Card>

        {formError && (
          <div
            role="alert"
            className="rounded-xl bg-red-50 border border-red-100 p-4 text-sm text-red-700"
          >
            {formError}
          </div>
        )}

        {mlItemError && (
          <div
            role="alert"
            className="fixed inset-0 z-50 flex items-center justify-center"
          >
            <div
              className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700 max-w-md w-full shadow-lg"
            >
              <h3 className="text-lg font-semibold mb-2">
                Erro ao carregar do Mercado Livre
              </h3>
              <p className="text-sm mb-4">
                Não foi possível buscar as imagens e dados do anúncio no
                Mercado Livre. Verifique sua conexão e o token de integração.
              </p>
              <div className="flex justify-end gap-2">
                <Button
                  variant="secondary"
                  onClick={handleRetry}
                  className="text-red-700 hover:bg-red-100"
                >
                  Tentar novamente
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </WizardContext.Provider>
  );
}