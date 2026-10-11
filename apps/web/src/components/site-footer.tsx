import { ArrowSwipe, SECTION_X } from "./crafto";
import { Logo } from "./logo";
import { NAV } from "./site-header";

export const CONTACT_EMAIL = "bonjour@jeflink.sn";

export function SiteFooter() {
  return (
    <footer className={`footer-dark bg-dark-gray overflow-hidden ${SECTION_X}`}>
      <div className="container-fluid">
        <div className="footer-top border-bottom border-color-transparent-white-light pb-50px mb-50px md-pb-30px md-mb-30px">
          <div className="row align-items-center">
            <div className="col-lg-6 md-mb-20px text-center text-lg-start">
              <ul className="footer-navbar fs-16 lh-normal">
                {NAV.map((item) => (
                  <li key={item.href} className="nav-item">
                    <a href={item.href} className="nav-link">
                      {item.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
            <div className="col-lg-6 d-flex align-items-center justify-content-center justify-content-lg-end">
              <div className="hover-arrow-swipe d-flex align-items-center last-paragraph-no-margin">
                <a
                  href={`mailto:${CONTACT_EMAIL}`}
                  className="alt-font fs-60 lg-fs-45 xl-fs-55 text-white d-inline-block align-middle"
                >
                  {CONTACT_EMAIL}
                </a>
                <ArrowSwipe size={30} className="ms-5px position-relative top-5px" />
              </div>
            </div>
          </div>
        </div>
        <div className="row justify-content-center text-center text-lg-start mb-5 sm-mb-40px">
          <div className="col-lg-3 col-sm-6 md-mb-30px">
            <span className="fw-500 text-white d-block mb-5px">Dakar</span>
            <p className="mb-0">
              Ouakam, Mermoz, Plateau, <br /> Liberté, Grand Yoff, Médina…
            </p>
          </div>
          <div className="col-lg-3 col-sm-6 md-mb-30px">
            <span className="fw-500 text-white d-block mb-5px">Banlieue</span>
            <p className="mb-0">
              Pikine, Guédiawaye, <br /> Parcelles Assainies, Keur Massar…
            </p>
          </div>
          <div className="col-xl-2 col-lg-3 col-sm-6 offset-xl-2 xs-mb-30px">
            <span className="fw-500 text-white d-block mb-5px">Nous écrire</span>
            <p className="m-0">
              <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
            </p>
            <p className="m-0">Lun–sam, 8 h–20 h</p>
          </div>
          <div className="col-xl-2 col-lg-3 col-sm-6 last-paragraph-no-margin">
            <span className="fw-500 text-white d-block mb-5px">Espace pro</span>
            <ul className="social fs-16">
              <li>
                <a href="/inscription?role=pro">Devenir pro</a>
              </li>
              <li>
                <a href="/connexion">Se connecter</a>
              </li>
            </ul>
          </div>
        </div>
        <div className="row align-items-end justify-content-center text-center text-lg-start">
          <div className="col-10 col-sm-7 col-md-6 col-lg-7 col-xxl-8 md-mb-30px">
            <a href="/" className="footer-logo text-white" aria-label="Jeflink, accueil">
              <Logo id="footer" className="jeflink-logo-xl" />
            </a>
          </div>
          <div className="col-lg-5 col-xxl-4">
            <p className="md-mb-0">
              © {new Date().getFullYear()} Jeflink. Le bon pro, au bon prix, travail garanti.
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
}
