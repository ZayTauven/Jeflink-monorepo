"use client";

import { useEffect, useState, type ChangeEvent } from "react";

import { shrinkImage } from "./image-input";

/**
 * Photos jointes à une demande (3 au plus) : réduites dans le navigateur, aperçus en vignettes.
 * Au-delà du maximum, les premières sont gardées et le client est prévenu.
 */
export function PhotosInput({
  id,
  name,
  max = 3,
  describedBy,
}: {
  id: string;
  name: string;
  max?: number;
  describedBy?: string;
}) {
  const [previews, setPreviews] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => () => previews.forEach((url) => URL.revokeObjectURL(url)), [previews]);

  async function onChange(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const chosen = Array.from(input.files ?? []);
    const kept = chosen.slice(0, max);
    // Réduction : 1 à 3 s sur un petit téléphone ; l'envoi attend (sinon les originaux partent).
    const submit = input.form?.querySelector<HTMLButtonElement>('button[type="submit"]');
    setBusy(true);
    if (submit) submit.disabled = true;
    setNote(
      chosen.length > max ? `${max} photos au plus : les ${max} premières sont gardées.` : "",
    );
    const small = await Promise.all(kept.map((file) => shrinkImage(file)));
    const list = new DataTransfer();
    small.forEach((file) => list.items.add(file));
    input.files = list.files;
    setPreviews(small.map((file) => URL.createObjectURL(file)));
    setBusy(false);
    if (submit) submit.disabled = false;
  }

  return (
    <>
      <input
        id={id}
        name={name}
        type="file"
        multiple
        // Sans « image/heic » : l'iPhone convertit sa photo en JPEG avant de la donner.
        accept="image/jpeg,image/png,image/webp"
        className="form-control"
        aria-describedby={describedBy}
        onChange={onChange}
      />
      {/* Toujours rendu : un message qui change dans une zone déjà là est bien annoncé. */}
      <div className="hint text-dark-gray" role="status" aria-live="polite">
        {busy ? "Préparation des photos…" : note}
      </div>
      {previews.length > 0 && (
        <div className="jf-photos mt-10px">
          {previews.map((url, i) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={url} src={url} alt={`Photo ${i + 1} choisie`} className="jf-photo" />
          ))}
        </div>
      )}
    </>
  );
}
