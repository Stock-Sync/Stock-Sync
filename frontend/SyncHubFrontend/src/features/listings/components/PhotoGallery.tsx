import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Loader2, Trash2 } from "lucide-react";

export interface PhotoItem {
  source: string;
}

export interface PhotoGalleryProps {
  value: PhotoItem[];
  onChange: (items: PhotoItem[]) => void;
  maxFiles?: number;
  disabled?: boolean;
  label?: string;
}

/**
 * Galeria de fotos do anúncio: seleção via Cloudinary, remoção e reordenação.
 * O Mercado Livre aceita no máximo 12 imagens por anúncio.
 */
export function PhotoGallery({
  value,
  onChange,
  maxFiles = 12,
  disabled = false,
  label = "Fotos do anúncio",
}: PhotoGalleryProps) {
  const [isUploading, setIsUploading] = useState(false);
  const [widgetLoading, setWidgetLoading] = useState(true);
  const widgetLoaded = useRef(false);

  useEffect(() => {
    if (widgetLoaded.current || !import.meta.env.VITE_CLOUDINARY_CLOUD_NAME) {
      setWidgetLoading(false);
      return;
    }
    const script = document.createElement("script");
    script.src = "https://widget.cloudinary.com/v2.0/global/all.js";
    script.async = true;
    script.onload = () => {
      widgetLoaded.current = true;
      setWidgetLoading(false);
    };
    script.onerror = () => {
      console.error("Failed to load Cloudinary widget");
      setWidgetLoading(false);
    };
    document.body.appendChild(script);
    return () => {
      document.body.removeChild(script);
      setWidgetLoading(false);
    };
  }, []);

  const notConfigured =
    !import.meta.env.VITE_CLOUDINARY_CLOUD_NAME ||
    !import.meta.env.VITE_CLOUDINARY_UPLOAD_PRESET;

  const openWidget = useCallback(() => {
    if (!window.cloudinary || isUploading || value.length >= maxFiles) {
      return;
    }
    setIsUploading(true);

    window.cloudinary.createUploadWidget(
      {
        cloudName: import.meta.env.VITE_CLOUDINARY_CLOUD_NAME,
        uploadPreset: import.meta.env.VITE_CLOUDINARY_UPLOAD_PRESET,
        folder: "stocksync/listings",
        maxFiles: maxFiles - value.length,
        multiple: true,
        resourceType: "image",
        clientAllowedFormats: ["jpg", "jpeg", "png", "webp"],
        maxFileSize: 10_000_000,
        showPoweredBy: false,
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (error: any, result: any) => {
        if (error) {
          console.error("Cloudinary upload error:", error);
          setIsUploading(false);
          return;
        }
        if (result && result.event === "success") {
          onChange([...value, { source: result.info.secure_url }]);
        }
        if (result && result.event === "close") {
          setIsUploading(false);
        }
      }
    ).open();
  }, [maxFiles, isUploading, onChange, value]);

  const move = useCallback(
    (index: number, direction: -1 | 1) => {
      const target = index + direction;
      if (target < 0 || target >= value.length) {
        return;
      }
      const items = [...value];
      const [moved] = items.splice(index, 1);
      items.splice(target, 0, moved);
      onChange(items);
    },
    [value, onChange]
  );

  const remove = useCallback(
    (index: number) => {
      onChange(value.filter((_, i) => i !== index));
    },
    [value, onChange]
  );

  const buttonDisabled =
    disabled ||
    isUploading ||
    value.length >= maxFiles ||
    widgetLoading ||
    notConfigured ||
    !window.cloudinary;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-600">{label}</span>
        <span className="text-xs font-mono text-slate-400">
          {value.length}/{maxFiles}
        </span>
      </div>

      {notConfigured && (
        <p className="text-xs text-amber-600 bg-amber-50 rounded p-2">
          Variáveis de nuvem do Cloudinary não configuradas
          (VITE_CLOUDINARY_CLOUD_NAME e VITE_CLOUDINARY_UPLOAD_PRESET). O
          envio de fotos estará indisponível até configurá-las.
        </p>
      )}

      <button
        type="button"
        onClick={openWidget}
        disabled={buttonDisabled}
        className={`
          relative w-16 h-16 rounded-lg border-2 flex items-center justify-center
          bg-slate-50 transition-colors cursor-pointer
          ${buttonDisabled
            ? "border-dashed border-line text-slate-400 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
            : "border-dashed border-brand-500 hover:border-brand-500 hover:bg-brand-50"}
        `}
      >
        {widgetLoading && (
          <Loader2 className="h-4 w-4 animate-spin text-brand-600" />
        )}
        {!widgetLoading && <span className="text-center text-xs text-slate-500">+ Adicionar</span>}
      </button>

      {value.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-4">
          {value.map((photo, index) => (
            <div
              key={index}
              className="relative w-full aspect-square rounded-xl border border-line overflow-hidden bg-slate-50"
            >
              <img
                src={photo.source}
                alt={`Foto ${index + 1}`}
                className="w-full h-full object-cover"
              />
              <button
                type="button"
                onClick={() => remove(index)}
                aria-label={`Remover foto ${index + 1}`}
                className="absolute top-1 right-1 rounded-full bg-red-500 text-white text-xs p-1 hover:bg-red-600"
              >
                <Trash2 className="h-3 w-3" />
              </button>
              <div className="flex h-full w-full items-end justify-between p-1">
                <button
                  type="button"
                  onClick={() => move(index, -1)}
                  disabled={index === 0 || disabled}
                  className="p-1 text-slate-400 hover:bg-slate-200 rounded disabled:opacity-40"
                  aria-label="Mover para cima"
                >
                  <ChevronUp className="h-3 w-3" />
                </button>
                <button
                  type="button"
                  onClick={() => move(index, 1)}
                  disabled={index === value.length - 1 || disabled}
                  className="p-1 text-slate-400 hover:bg-slate-200 rounded disabled:opacity-40"
                  aria-label="Mover para baixo"
                >
                  <ChevronDown className="h-3 w-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {value.length === 0 && !notConfigured && !widgetLoading && (
        <p className="text-xs text-slate-500">
          Pelo menos 1 foto é obrigatória para publicar o anúncio.
        </p>
      )}
    </div>
  );
}
