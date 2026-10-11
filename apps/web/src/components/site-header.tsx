import { getToken } from "@/lib/api";

import { Logo } from "./logo";

export const NAV = [
  { href: "/", label: "Accueil" },
  { href: "/a-propos", label: "À propos" },
  { href: "/metiers", label: "Métiers" },
  { href: "/services", label: "Comment ça marche" },
  { href: "/contact", label: "Contact" },
];

/** En-tête Crafto « Marketing strategy » : logo, bouton, menu plein écran (hamburger). */
export async function SiteHeader({ bordered = false }: { bordered?: boolean }) {
  const signedIn = Boolean(await getToken());
  const account = signedIn
    ? { href: "/espace", label: "Mon espace" }
    : { href: "/connexion", label: "Se connecter" };
  return (
    <header>
      <nav
        className={`navbar navbar-expand-lg header-transparent bg-transparent disable-fixed${bordered ? " border-bottom border-color-transparent-dark-light" : ""}`}
      >
        <div className="container-fluid p-0">
          <div className="col-auto col-lg-3 me-lg-0 me-auto ps-md-0">
            <a className="navbar-brand" href="/" aria-label="Jeflink, accueil">
              <Logo id="header" />
            </a>
          </div>
          <div className="col-auto col-lg-3 text-end pe-0">
            <div className="header-icon">
              <div className="header-button">
                <a
                  href={account.href}
                  className="btn btn-small btn-rounded btn-transparent-light-gray bg-transparent border-color-transparent-dark-light"
                >
                  <span className="indicator me-10px" />
                  {account.label}
                </a>
              </div>
              <div className="header-push-button hamburger-push-button icon sm-pe-15px">
                <div className="push-button" role="button" aria-label="Ouvrir le menu">
                  <span /> <span /> <span /> <span />
                </div>
              </div>
            </div>
          </div>
        </div>
      </nav>
      <div className="push-menu hamburger-nav hamburger-menu-simple header-light bg-narvik">
        <span className="close-menu bg-narvik" role="button" aria-label="Fermer le menu">
          <i className="fa-solid fa-xmark text-dark-gray" />
        </span>{" "}
        <div className="container h-100">
          <div className="row align-items-center justify-content-center h-100">
            <div className="col-xl-7 col-lg-7 col-md-6 d-none d-lg-inline-block">
              <span className="alt-font fs-120 lg-fs-100 lh-100 lg-lh-90 ls-minus-3px w-90 d-block">
                Des pros vérifiés, à Dakar.
              </span>
            </div>
            <div className="col-xl-4 col-lg-4 offset-xl-1 col-md-5 text-center text-md-start">
              <div
                className="hamburger-menu menu-list-wrapper"
                data-scroll-options='{ "theme": "light" }'
              >
                <ul className="menu-item-list alt-font p-0 text-center text-lg-start">
                  {[...NAV, account].map((item) => (
                    <li key={item.href} className="menu-item">
                      <a href={item.href} className="nav-link">
                        {item.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            <div className="col-12 menu-text text-center pt-3 pb-3 order-3 d-none d-lg-inline-block">
              <div className="divider-style-03 divider-style-03-01 border-color-transparent-dark-light mb-3" />{" "}
              <span className="alt-font fs-22 sm-fs-20 fw-300 d-inline-block align-middle mb-0 text-dark-gray">
                Un besoin à la maison ?
              </span>{" "}
              <div className="separator-line-1px d-inline-block align-middle ms-20px me-20px mt-5px w-70px bg-dark-gray" />{" "}
              <a
                href="/espace/demandes/nouvelle"
                className="text-dark-gray alt-font fs-22 sm-fs-20 fw-300 d-inline-block align-middle"
              >
                Faire une demande
              </a>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
