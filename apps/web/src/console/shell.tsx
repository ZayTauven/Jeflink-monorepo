"use client";

/**
 * Coque de la console : barre latérale, en-tête, recherche (Ctrl K), thème clair/sombre.
 * Balisage et classes du template vireo (.ax-*), habillage Crafto dans console.css.
 * Ici, navigation par next/link : la console ne charge pas les scripts Crafto.
 */
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";

import { LogoMark } from "@/components/logo";
import type { Me } from "@/lib/types";

import { navFor, type NavItem } from "./nav";
import { COLLAPSED_KEY, THEME_KEY } from "./theme";
import type { Badges } from "./types";
import { plural } from "./text";

const PHONE = "(max-width: 767.98px)";

function store(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Navigation privée : le réglage vaut pour la page en cours seulement.
  }
}

function isActive(pathname: string, href: string) {
  return href === "/console" ? pathname === href : pathname.startsWith(href);
}

export function ConsoleShell({
  me,
  badges,
  children,
}: {
  // Le strict nécessaire côté navigateur : identité affichée et rubriques ouvertes au rôle.
  me: Pick<Me, "first_name" | "last_name" | "email" | "console_sections">;
  badges: Badges;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const toggle = useRef<HTMLButtonElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  const [phone, setPhone] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [search, setSearch] = useState(false);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const html = document.documentElement;
    setDark(html.getAttribute("data-ax-theme") === "dark");
    setCollapsed(html.hasAttribute("data-ax-collapsed"));
    const mq = window.matchMedia(PHONE);
    const onMedia = () => {
      setPhone(mq.matches);
      if (!mq.matches) setDrawer(false);
    };
    onMedia();
    mq.addEventListener("change", onMedia);
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearch(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      mq.removeEventListener("change", onMedia);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  // Tiroir mobile : refermé à chaque changement de page.
  useEffect(() => setDrawer(false), [pathname]);
  useEffect(() => {
    const html = document.documentElement;
    if (!drawer) return html.removeAttribute("data-ax-drawer");
    html.setAttribute("data-ax-drawer", "open");
    sidebar.current?.querySelector<HTMLElement>("a")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setDrawer(false);
      toggle.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawer]);

  const toggleMenu = () => {
    if (phone) return setDrawer((d) => !d);
    const next = !collapsed;
    document.documentElement.toggleAttribute("data-ax-collapsed", next);
    store(COLLAPSED_KEY, next ? "1" : "0");
    setCollapsed(next);
  };

  const toggleTheme = () => {
    const next = !dark;
    document.documentElement.setAttribute("data-ax-theme", next ? "dark" : "light");
    store(THEME_KEY, next ? "dark" : "light");
    setDark(next);
    document.dispatchEvent(new Event("ax:change")); // les graphiques vireo relisent leurs couleurs
  };

  const nav = navFor(me.console_sections);
  const ops = me.console_sections.includes("operations");
  const pending =
    badges.pros_pending + badges.stale_requests + badges.contact_unhandled + badges.disputes_active;
  const fullName = `${me.first_name} ${me.last_name}`.trim();

  return (
    <>
      <a className="jf-skip" href="#contenu">
        Aller au contenu
      </a>
      <div className="ax-layout">
        <aside
          ref={sidebar}
          id="jf-sidebar"
          className="ax-sidebar"
          aria-label="Console Jeflink"
          // Sur téléphone, le menu fermé est hors écran : on le retire aussi du clavier.
          inert={phone && !drawer}
        >
          <div className="ax-sidebar__brand">
            <Link
              className="ax-sidebar__logo"
              href="/console"
              aria-label="Console Jeflink, accueil"
            >
              <span className="ax-sidebar__mark jf-console-mark" aria-hidden="true">
                <LogoMark id="console" />
              </span>
              <span className="ax-sidebar__wordmark">
                jeflink <small>console</small>
              </span>
            </Link>
          </div>
          <nav className="ax-sidebar__nav" aria-label="Menu de la console">
            {nav.map((section) => (
              <div key={section.title}>
                <p className="ax-sidebar__section">{section.title}</p>
                {section.items.map((item) => (
                  <NavLink
                    key={item.href}
                    item={item}
                    active={isActive(pathname, item.href)}
                    count={item.badge ? badges[item.badge] : 0}
                  />
                ))}
              </div>
            ))}
          </nav>
        </aside>
        {drawer && (
          <button
            type="button"
            className="ax-backdrop"
            aria-label="Fermer le menu"
            tabIndex={-1}
            onClick={() => setDrawer(false)}
          />
        )}

        <div className="ax-shell">
          <header className="ax-header">
            <button
              ref={toggle}
              type="button"
              className="ax-nav-toggle ax-icon-btn"
              onClick={toggleMenu}
              aria-label="Menu"
              aria-controls="jf-sidebar"
              aria-expanded={phone ? drawer : !collapsed}
            >
              <i className="bi bi-list" aria-hidden="true" />
            </button>
            <button
              type="button"
              className="ax-search"
              onClick={() => setSearch(true)}
              aria-haspopup="dialog"
            >
              <i className="bi bi-search ax-search__icon" aria-hidden="true" />
              <span className="ax-search__placeholder">Rechercher une rubrique…</span>
              <kbd className="ax-search__keycap">Ctrl K</kbd>
            </button>
            <span className="ax-header__spacer" />
            <a className="ax-icon-btn" href="/" aria-label="Voir le site" title="Voir le site">
              <i className="bi bi-box-arrow-up-right" aria-hidden="true" />
            </a>
            <button
              type="button"
              className="ax-icon-btn"
              onClick={toggleTheme}
              aria-pressed={dark}
              aria-label="Mode sombre"
              title={dark ? "Passer en mode clair" : "Passer en mode sombre"}
            >
              <i className={`bi ${dark ? "bi-sun" : "bi-moon-stars"}`} aria-hidden="true" />
            </button>
            {ops && (
              <Dropdown
                className="ax-notif"
                panelClassName="ax-dropdown ax-notif__menu"
                label={`À traiter : ${pending}`}
                buttonClassName="ax-icon-btn ax-notif__trigger"
                button={
                  <>
                    <i className="bi bi-bell" aria-hidden="true" />
                    {pending > 0 && (
                      <span className="ax-badge-count" aria-hidden="true">
                        {pending}
                      </span>
                    )}
                  </>
                }
              >
                <div className="ax-dropdown__head">
                  <span>À traiter</span>
                </div>
                <ul className="ax-notif__list">
                  <Todo href="/console/pros" icon="bi-person-badge">
                    {plural(badges.pros_pending, "pro à vérifier", "pros à vérifier")}
                  </Todo>
                  <Todo href="/console/demandes?sans_devis=1" icon="bi-hourglass-split">
                    {plural(
                      badges.stale_requests,
                      "demande sans devis à relancer",
                      "demandes sans devis à relancer",
                    )}
                  </Todo>
                  <Todo href="/console/litiges" icon="bi-exclamation-triangle">
                    {plural(badges.disputes_active, "litige en cours", "litiges en cours")}
                  </Todo>
                  <Todo href="/console/messages" icon="bi-chat-left-text">
                    {plural(
                      badges.contact_unhandled,
                      "message de contact à lire",
                      "messages de contact à lire",
                    )}
                  </Todo>
                </ul>
              </Dropdown>
            )}
            <Dropdown
              menu
              className="ax-profile"
              panelClassName="ax-dropdown ax-profile__menu"
              label="Mon compte"
              buttonClassName="ax-profile__trigger"
              button={<Initials name={fullName} />}
            >
              <div className="ax-profile__card">
                <Initials name={fullName} />
                <span className="ax-profile__card-meta">
                  <b>{fullName}</b>
                  <small>{me.email}</small>
                </span>
              </div>
              <a className="ax-dropdown__item" role="menuitem" href="/">
                Voir le site
              </a>
              <div className="ax-dropdown__divider" role="separator" />
              <form action="/act/logout" method="post" role="none">
                <button
                  type="submit"
                  className="ax-dropdown__item ax-dropdown__item--danger"
                  role="menuitem"
                >
                  Se déconnecter
                </button>
              </form>
            </Dropdown>
          </header>

          <main className="ax-main" id="contenu" tabIndex={-1}>
            {children}
          </main>
          <footer className="ax-footer">
            <div className="ax-footer__left">
              <span className="ax-footer__copy">© {new Date().getFullYear()} Jeflink</span>
              <span className="ax-footer__sep" aria-hidden="true">
                ·
              </span>
              <span>Console de démo</span>
            </div>
          </footer>
        </div>
      </div>
      {search && (
        <SearchDialog
          items={nav.flatMap((section) => section.items)}
          onClose={() => setSearch(false)}
        />
      )}
    </>
  );
}

function NavLink({ item, active, count }: { item: NavItem; active: boolean; count: number }) {
  return (
    <Link
      href={item.href}
      className={`ax-nav__item ax-nav__item--single${active ? " ax-nav__item--active is-active" : ""}`}
      aria-current={active ? "page" : undefined}
      title={item.label}
    >
      <span className="ax-nav__bar" aria-hidden="true" />
      <i className={`bi ${item.icon} ax-nav__icon`} aria-hidden="true" />
      <span className="ax-nav__label">{item.label}</span>
      {count > 0 ? (
        <span className="ax-nav__badge ax-nav__badge--count">{count}</span>
      ) : item.lot ? (
        <span className="ax-nav__badge jf-nav-soon">Bientôt</span>
      ) : null}
    </Link>
  );
}

function Todo({ href, icon, children }: { href: string; icon: string; children: ReactNode }) {
  return (
    <li className="ax-notif__row">
      <span className="ax-notif__chip">
        <i className={`bi ${icon}`} aria-hidden="true" />
      </span>
      <Link className="ax-notif__body" href={href}>
        <b className="ax-notif__title">{children}</b>
      </Link>
    </li>
  );
}

function Initials({ name }: { name: string }) {
  const letters = name
    .split(" ")
    .filter(Boolean)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <span className="ax-avatar jf-initials" aria-hidden="true">
      {letters || "J"}
    </span>
  );
}

/**
 * Panneau déroulant : fermé au clic extérieur et à Échap (le focus revient au bouton).
 * `menu` : vrai menu d'actions (rôle ARIA menu, focus sur le premier élément à l'ouverture).
 */
function Dropdown({
  menu = false,
  className,
  panelClassName,
  buttonClassName,
  label,
  button,
  children,
}: {
  menu?: boolean;
  className: string;
  panelClassName: string;
  buttonClassName: string;
  label: string;
  button: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    if (menu) wrap.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const onPointer = (e: PointerEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      trigger.current?.focus();
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, menu]);

  return (
    <div className={className} ref={wrap}>
      <button
        ref={trigger}
        type="button"
        className={buttonClassName}
        aria-label={label}
        aria-haspopup={menu ? "menu" : "true"}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((o) => !o)}
      >
        {button}
      </button>
      {open && (
        <div id={panelId} className={panelClassName} role={menu ? "menu" : undefined}>
          {children}
        </div>
      )}
    </div>
  );
}

/** Recherche des rubriques (Ctrl K) : filtre le menu par nom et mots-clés. Motif combobox. */
function SearchDialog({ items, onClose }: { items: NavItem[]; onClose: () => void }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const results = useMemo(() => {
    const query = q.trim().toLowerCase();
    if (!query) return items;
    return items.filter(
      (i) =>
        i.label.toLowerCase().includes(query) ||
        (i.keywords ?? []).some((k) => k.toLowerCase().includes(query)),
    );
  }, [q, items]);

  // Focus dans le champ à l'ouverture, rendu à l'élément d'origine à la fermeture.
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    input.current?.focus();
    return () => before?.focus();
  }, []);
  useEffect(() => setActive(0), [q]);

  const go = (item: NavItem) => {
    onClose();
    router.push(item.href);
  };
  const optionId = (i: number) => `${listId}-${i}`;

  return (
    <div
      className="ax-command is-open"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
        else if (e.key === "Tab")
          e.preventDefault(); // le focus reste dans la boîte
        else if (e.key === "ArrowDown") {
          e.preventDefault();
          setActive((a) => Math.min(a + 1, results.length - 1));
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          setActive((a) => Math.max(a - 1, 0));
        } else if (e.key === "Enter" && results[active]) {
          e.preventDefault();
          go(results[active]);
        }
      }}
    >
      <button
        type="button"
        className="ax-command__backdrop"
        aria-label="Fermer"
        tabIndex={-1}
        onClick={onClose}
      />
      <div className="ax-command__panel" role="dialog" aria-modal="true" aria-label="Rechercher">
        <div className="ax-command__input">
          <i className="bi bi-search" aria-hidden="true" />
          <input
            ref={input}
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={results[active] ? optionId(active) : undefined}
            placeholder="Une rubrique : Pros, Avis, Réglages…"
            aria-label="Rechercher une rubrique"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <p className="ax-visually-hidden" aria-live="polite">
          {plural(results.length, "rubrique trouvée", "rubriques trouvées")}
        </p>
        <div className="ax-command__results" role="listbox" id={listId}>
          {results.length === 0 && <p className="ax-command__empty">Aucune rubrique trouvée.</p>}
          {results.map((item, i) => (
            <button
              key={item.href}
              id={optionId(i)}
              type="button"
              role="option"
              tabIndex={-1}
              aria-selected={i === active}
              className={`ax-command__row${i === active ? " is-active" : ""}`}
              onMouseEnter={() => setActive(i)}
              onClick={() => go(item)}
            >
              <span className="ax-command__row-title">
                <i className={`bi ${item.icon} me-2`} aria-hidden="true" /> {item.label}
              </span>
              {item.lot && <span className="ax-command__crumb">Bientôt</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
