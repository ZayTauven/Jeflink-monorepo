"use client";

import { useEffect, useState, type ChangeEvent } from "react";

/**
 * Réduit une photo dans le navigateur avant l'envoi : une photo de téléphone (3 à 8 Mo) part en
 * WebP de quelques centaines de Ko, ce qui compte avec un forfait mobile. Redessinée sur un
 * canevas, elle perd aussi ses métadonnées (position GPS). L'API refait de toute façon le travail
 * (jeflink/media.py) : en cas d'échec ici, le fichier d'origine part tel quel.
 */
export async function shrinkImage(file: File, maxSide = 1600): Promise<File> {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type)) return file;
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((done) => canvas.toBlob(done, "image/webp", 0.85));
    // Navigateur sans WebP (il rend du PNG, plus lourd) : on garde l'original.
    if (!blob || blob.type !== "image/webp" || blob.size >= file.size) return file;
    return new File([blob], `${file.name.replace(/\.[^.]*$/, "") || "photo"}.webp`, {
      type: "image/webp",
    });
  } catch {
    return file;
  }
}

/**
 * Champ fichier image : aperçu immédiat, photo réduite avant l'envoi. `autoSubmit` : le
 * formulaire part dès la photo choisie (prévoir un bouton d'envoi pour le cas sans JavaScript).
 */
export function ImageInput({
  id,
  name,
  current = "",
  maxSide,
  className,
  previewClassName,
  previewSize,
  previewAlt = "",
  autoSubmit = false,
  required = false,
  "aria-describedby": describedBy,
}: {
  id: string;
  name: string;
  current?: string;
  maxSide?: number;
  className?: string;
  previewClassName?: string;
  previewSize?: number;
  /** Texte de l'aperçu ; vide quand le libellé du champ suffit. */
  previewAlt?: string;
  autoSubmit?: boolean;
  required?: boolean;
  "aria-describedby"?: string;
}) {
  const [preview, setPreview] = useState(current);

  // Libère l'aperçu local (blob:) quand il est remplacé ou que le champ disparaît.
  useEffect(
    () => () => {
      if (preview.startsWith("blob:")) URL.revokeObjectURL(preview);
    },
    [preview],
  );

  async function onChange(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    const small = await shrinkImage(file, maxSide);
    if (small !== file) {
      const list = new DataTransfer();
      list.items.add(small);
      input.files = list.files;
    }
    setPreview(URL.createObjectURL(small));
    if (autoSubmit) input.form?.requestSubmit();
  }

  return (
    <>
      {preview && previewClassName && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          className={previewClassName}
          src={preview}
          alt={preview === current ? previewAlt : ""}
          width={previewSize}
          height={previewSize}
          // Fichier illisible (pas une vraie image) : on revient à l'image actuelle.
          onError={() => setPreview(current)}
        />
      )}
      <input
        id={id}
        name={name}
        type="file"
        // Sans « image/heic » : l'iPhone convertit sa photo en JPEG avant de la donner.
        accept="image/jpeg,image/png,image/webp"
        className={className}
        required={required}
        aria-describedby={describedBy}
        onChange={onChange}
      />
    </>
  );
}
