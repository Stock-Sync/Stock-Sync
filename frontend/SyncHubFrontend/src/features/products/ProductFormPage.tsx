import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Card, CardBody, CardFooter } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { Textarea } from "../../components/ui/Textarea";
import { PageHeader } from "../../components/ui/PageHeader";
import { LoadingBlock } from "../../components/ui/Spinner";
import { EmptyState } from "../../components/ui/EmptyState";
import { useToast } from "../../components/ui/toast-context";
import { parseDecimal } from "../../lib/format";
import { paths } from "../../routes/paths";
import { ApiError } from "../../types/api";
import { EMPTY_PRODUCT_FORM } from "../../types/view-models";
import type { ProductFormValues, ProductView } from "../../types/view-models";
import {
  useCreateProduct,
  useProductView,
  useUpdateProduct,
} from "./queries";
import { CloudinaryUploader } from "../../components/ui/CloudinaryUploader";

type FormErrors = Partial<Record<keyof ProductFormValues, string>>;

function validate(values: ProductFormValues): FormErrors {
  const errors: FormErrors = {};

  if (values.sku.trim().length === 0) {
    errors.sku = "Informe o SKU do produto.";
  }
  if (values.title.trim().length === 0) {
    errors.title = "Informe o título do produto.";
  }
  if (values.description.trim().length === 0) {
    errors.description = "Informe a descrição do produto.";
  }
  if (values.price.trim().length === 0) {
    errors.price = "Informe o preço do produto.";
  } else if (Number.isNaN(parseDecimal(values.price))) {
    errors.price = "Preço inválido. Use apenas números.";
  } else if (parseDecimal(values.price) < 0) {
    errors.price = "O preço não pode ser negativo.";
  }
  if (values.stockQuantity.trim().length === 0) {
    errors.stockQuantity = "Informe a quantidade em estoque.";
  }
  if (values.pictures.length === 0) {
    errors.pictures = "Adicione pelo menos uma imagem.";
  }

  return errors;
}

interface ProductFormFieldsProps {
  mode: "create" | "edit";
  initial: ProductFormValues;
  isSubmitting: boolean;
  serverErrors?: FormErrors;
  onSubmit: (values: ProductFormValues) => Promise<void>;
  onCancel: () => void;
}

function ProductFormFields({
  mode,
  initial,
  isSubmitting,
  serverErrors,
  onSubmit,
  onCancel,
}: ProductFormFieldsProps) {
  const [values, setValues] = useState<ProductFormValues>(initial);
  const [errors, setErrors] = useState<FormErrors>({});
  const merged = { ...errors, ...serverErrors };

  const setField =
    (field: keyof ProductFormValues) =>
    (event: { target: { value: string } }) => {
      setValues((current) => ({ ...current, [field]: event.target.value }));
      setErrors((current) => ({ ...current, [field]: undefined }));
    };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const found = validate(values);
    if (Object.keys(found).length > 0) {
      setErrors(found);
      return;
    }
    await onSubmit(values);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5" noValidate>
      <div className="space-y-5">
        {/* Seção 1: Dados Básicos */}
        <section className="space-y-4">
          <h3 className="text-sm font-semibold text-slate-800">Dados Básicos</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="SKU do Produto"
              name="sku"
              value={values.sku}
              onChange={setField("sku")}
              error={merged.sku}
              placeholder="Ex: CAB-LAN-10M"
              required
            />
            <Input
              label="Título do Produto"
              name="title"
              value={values.title}
              onChange={setField("title")}
              error={merged.title}
              placeholder="Ex: Cabo de Rede Cat6 Azul 10 Metros"
              required
            />
          </div>

          <Textarea
            label="Descrição"
            name="description"
            value={values.description}
            onChange={setField("description")}
            error={merged.description}
            placeholder="Descrição detalhada do produto"
            rows={3}
            required
          />

          <div className="grid gap-4 sm:grid-cols-3">
            <Input
              label="Preço Base (R$)"
              name="price"
              inputMode="decimal"
              value={values.price}
              onChange={setField("price")}
              error={merged.price}
              placeholder="0,00"
              required
            />
            <Input
              label="Quantidade em Estoque"
              name="stockQuantity"
              inputMode="numeric"
              value={values.stockQuantity}
              onChange={setField("stockQuantity")}
              error={merged.stockQuantity}
              placeholder="0"
              required
            />
          </div>
        </section>

        {/* Seção 2: Imagens */}
        <section className="space-y-4">
          <h3 className="text-sm font-semibold text-slate-800">Imagens do Produto</h3>
          <div className="space-y-2">
            <p className="text-sm text-slate-600">
              Mínimo 1 imagem, máximo 12. A primeira deve ter fundo branco (500x500px mínimo).
            </p>
            <CloudinaryUploader
              onUploadComplete={(urls) => setValues((current) => ({
                ...current,
                pictures: [...current.pictures, ...urls.map((url) => ({ source: url }))],
              }))}
              maxFiles={12}
              folder="stocksync/products"
            />
            {merged.pictures && (
              <p className="text-xs text-red-600" role="alert">{merged.pictures}</p>
            )}
          </div>
        </section>
      </div>

      <CardFooter>
        <Button variant="secondary" onClick={onCancel} disabled={isSubmitting}>
          Cancelar
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Salvando..." : mode === "create" ? "Criar" : "Salvar"}
        </Button>
      </CardFooter>
    </form>
  );
}

function toFormValues(product: ProductView): ProductFormValues {
  return {
    sku: product.sku,
    title: product.title,
    description: product.description,
    price: String(product.price),
    stockQuantity: String(product.stockQuantity),
    pictures: [],
  };
}

export function ProductFormPage({ mode }: { mode: "create" | "edit" }) {
  const { id } = useParams();
  const productId = Number(id);
  const navigate = useNavigate();
  const { notify } = useToast();

  const existing = useProductView(productId);
  const createProduct = useCreateProduct();
  const updateProduct = useUpdateProduct();

  const [serverErrors, setServerErrors] = useState<FormErrors>({});
  const current = existing.product;

  const submit = async (values: ProductFormValues) => {
    setServerErrors({});
    const payload = {
      sku: values.sku.trim(),
      title: values.title.trim(),
      description: values.description.trim(),
      price: parseDecimal(values.price),
      stockQuantity: parseDecimal(values.stockQuantity || "0"),
      pictures: values.pictures,
    };

    try {
      if (mode === "create") {
        const created = await createProduct.mutateAsync(payload);
        notify({
          tone: "success",
          title: "Produto criado",
          description: created.title,
        });
        navigate(paths.productDetail(created.id));
        return;
      }

      if (!current) {
        return;
      }
      await updateProduct.mutateAsync({
        id: current.productId,
        skuId: current.skuId,
        ...payload,
      });
      notify({ tone: "success", title: "Produto atualizado" });
      navigate(paths.productDetail(current.productId));
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "conflict") {
        setServerErrors({ sku: caught.message });
        return;
      }
      notify({
        tone: "error",
        title: "Não foi possível salvar o produto",
        description: caught instanceof ApiError ? caught.message : undefined,
      });
    }
  };

  if (mode === "edit" && existing.isPending) {
    return <LoadingBlock label="Carregando produto..." />;
  }

  if (mode === "edit" && !current) {
    return (
      <EmptyState
        title="Produto não encontrado"
        description="O produto pode ter sido removido."
      />
    );
  }

  const formKey = mode === "edit" && current ? String(current.id) : "new";

  return (
    <div className="space-y-6">
      <PageHeader
        title={mode === "create" ? "Novo Produto" : "Editar Produto"}
      />
      <Card>
        <CardBody>
          <ProductFormFields
            key={formKey}
            mode={mode}
            initial={mode === "edit" && current ? toFormValues(current) : EMPTY_PRODUCT_FORM}
            isSubmitting={createProduct.isPending || updateProduct.isPending}
            serverErrors={serverErrors}
            onSubmit={submit}
            onCancel={() => navigate(paths.products)}
          />
        </CardBody>
      </Card>
    </div>
  );
}