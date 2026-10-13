"use client";

/**
 * Liste de courts textes saisis en étiquettes (prestations d'un métier) : Entrée ajoute
 * (pas la virgule : une prestation peut en contenir), la croix retire, Retour arrière dans
 * le champ vide retire la dernière ; un collage de plusieurs lignes ajoute chaque ligne.
 * Ajouts, retraits et doublons sont annoncés aux lecteurs d'écran. Envoyé comme avant :
 * une valeur par ligne. Sans JavaScript, c'est la zone de texte d'origine (une par ligne).
 */
import { useEffect, useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";

const NBSP = " ";
const quoted = (text: string) => `«${NBSP}${text}${NBSP}»`;

export function TagsField({
  id,
  name,
  defaultValue,
  placeholder,
  "aria-describedby": describedBy,
}: {
  id: string;
  name: string;
  defaultValue: string[];
  placeholder: string;
  "aria-describedby"?: string;
}) {
  const [ready, setReady] = useState(false);
  const [items, setItems] = useState(defaultValue);
  const [draft, setDraft] = useState("");
  const [said, setSaid] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => setReady(true), []);

  if (!ready) {
    return (
      <textarea
        id={id}
        name={name}
        className="ax-textarea"
        rows={5}
        defaultValue={defaultValue.join("\n")}
        aria-describedby={describedBy}
      />
    );
  }

  function add(values: string[]) {
    const fresh = values.map((v) => v.trim()).filter(Boolean);
    const added = fresh.filter((v, i) => !items.includes(v) && fresh.indexOf(v) === i);
    setItems([...items, ...added]);
    setDraft("");
    if (added.length === 0) setSaid(`${quoted(fresh[0])} est déjà dans la liste.`);
    else if (added.length === 1) setSaid(`${quoted(added[0])} ajoutée.`);
    else setSaid(`${added.length} prestations ajoutées.`);
  }

  function remove(item: string) {
    setItems(items.filter((x) => x !== item));
    setSaid(`${quoted(item)} retirée.`);
    input.current?.focus(); // le bouton disparaît : le focus revient au champ
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && draft.trim()) {
      e.preventDefault();
      add([draft]);
    } else if (e.key === "Enter") {
      e.preventDefault(); // pas d'envoi du formulaire par erreur
    } else if (e.key === "Backspace" && !draft && items.length) {
      remove(items[items.length - 1]);
    }
  }

  function onPaste(e: ClipboardEvent<HTMLInputElement>) {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\n")) return;
    e.preventDefault();
    add(text.split(/\r?\n/));
  }

  return (
    <div className="jf-tags">
      {items.length > 0 && (
        <ul className="jf-tags__list" aria-label="Prestations ajoutées">
          {items.map((item) => (
            <li key={item} className="ax-badge ax-badge--soft ax-badge--chip jf-tag">
              {item}
              <button
                type="button"
                className="jf-tag__remove"
                onClick={() => remove(item)}
                aria-label={`Retirer ${quoted(item)}`}
              >
                <i className="bi bi-x-lg" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <input
        ref={input}
        id={id}
        className="ax-input"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onPaste={onPaste}
        onBlur={() => draft.trim() && add([draft])}
        placeholder={placeholder}
        aria-describedby={describedBy}
        autoComplete="off"
      />
      <input type="hidden" name={name} value={items.join("\n")} />
      <p className="ax-visually-hidden" role="status">
        {said}
      </p>
    </div>
  );
}
