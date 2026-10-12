import type { Metadata } from "next";

import { ActionForm } from "@/components/action-form";
import {
  ArrowSwipe,
  childsUp,
  fadeIn,
  fadeUp,
  lines,
  PERSPECTIVE,
  Pill,
  SECTION_X,
  SwitchSubmit,
  opt,
} from "@/components/crafto";
import { PageShell } from "@/components/page-shell";
import { CONTACT_EMAIL } from "@/components/site-footer";
import { getReviews, getStats } from "@/lib/api";
import { formatRating } from "@/lib/format";

export const metadata: Metadata = { title: "Contact" };

const IMG = "/crafto/images/demo-marketing-strategy";

const PLACES = [
  { name: "Dakar", text: "Ouakam, Mermoz, Plateau, Liberté, Grand Yoff, Médina, Point E…" },
  { name: "Banlieue", text: "Pikine, Guédiawaye, Parcelles Assainies, Keur Massar…" },
];

export default async function ContactPage({
  searchParams,
}: {
  searchParams: Promise<{ envoye?: string; erreur?: string }>;
}) {
  const [{ envoye, erreur }, reviews, stats] = await Promise.all([
    searchParams,
    getReviews(),
    getStats(),
  ]);
  const reviewers = reviews.filter((r) => r.author_photo).slice(0, 5);

  return (
    <PageShell>
      {/* Titre de page */}
      <section className={`${SECTION_X} pt-0 md-pt-50px pb-0 top-space-margin`}>
        <div className="container-fluid">
          <div className="row">
            <div className="col-md-5 col-xl-4 sm-mb-30px">
              <div className="bg-white border-radius-20px p-14 sm-p-7 xl-p-12 h-100 d-flex flex-column align-items-start">
                <Pill className="text-white bg-base-color mb-auto" anime={fadeUp()}>
                  Contact
                </Pill>{" "}
                <h1
                  className="h3 alt-font fw-500 ls-minus-2px mb-0 mt-30 md-mt-0 pt-70px"
                  style={PERSPECTIVE}
                  data-anime={lines()}
                >
                  Une question ? Écrivez-nous.
                </h1>
              </div>
            </div>
            <div className="col-md-7 col-xl-8" data-anime={fadeIn(300)}>
              <img
                className="border-radius-20px object-fit-cover h-100"
                src={opt(`${IMG}-contact-title.jpg`)}
                alt=""
              />
            </div>
          </div>
        </div>
      </section>

      {/* Bandeau email */}
      <section className={`${SECTION_X} py-0`}>
        <div className="container-fluid">
          <div
            className="row m-0 pt-40px pb-40px text-center justify-content-center border-bottom border-color-transparent-dark-light"
            data-anime={fadeUp(300)}
          >
            <div className="col-lg-12 col-md-11 alt-font fs-20 ls-0px d-block d-sm-inline-block">
              Une question sur une demande, un pro ou un partenariat ? Écrivez-nous à{" "}
              <a href={`mailto:${CONTACT_EMAIL}`} className="text-decoration-line-bottom fw-500">
                {CONTACT_EMAIL}
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Parlons-en */}
      <section className={SECTION_X}>
        <div className="container-fluid">
          <div className="row justify-content-between">
            <div className="col-lg-5 md-mb-50px sm-mb-40px" data-anime={fadeIn(150)}>
              <div className="overflow-visible position-relative h-100">
                <div
                  className="border-radius-15px d-flex align-items-end justify-content-center overflow-hidden cover-background h-100 md-h-500px xs-h-400px"
                  style={{ backgroundImage: `url('${opt(`${IMG}-contact-02.jpg`)}')` }}
                >
                  <div className="opacity-very-light bg-dark-gray" />
                </div>
                <div className="position-absolute top-0px left-0px w-100 h-100 z-index-9">
                  <a
                    href="/services"
                    aria-label="Voir comment ça marche"
                    className="absolute-middle-center text-center rounded-circle video-icon-box video-icon-extra-large"
                  >
                    <span>
                      <span className="video-icon bg-dark-gray">
                        <i className="bi bi-play-fill fs-50 text-white" />{" "}
                        <span className="video-icon-sonar">
                          <span className="video-icon-sonar-bfr bg-dark-gray opacity-9" />
                        </span>
                      </span>
                    </span>
                  </a>
                </div>
              </div>
            </div>
            <div className="col-lg-7 col-xl-6 offset-xl-1">
              <div
                className="feature-box feature-box-left-icon-middle last-paragraph-no-margin mb-20px"
                data-anime={fadeUp()}
              >
                <div className="feature-box-icon me-10px">
                  <i className="bi bi-asterisk icon-extra-medium text-base-color" />
                </div>
                <div className="feature-box-content">
                  <span className="alt-font fs-22">Parlons-en</span>
                </div>
              </div>
              <h2
                className="alt-font ls-minus-2px mb-0 w-95 fw-500"
                style={PERSPECTIVE}
                data-anime={lines()}
              >
                Nous répondons du lundi au samedi, en français ou en wolof.
              </h2>
              <div
                className="hover-arrow-swipe d-flex align-items-center justify-content-between border-top border-color-dark-gray pt-30px mt-18 md-mt-30px"
                data-anime={fadeUp()}
              >
                <span className="fs-20 sm-fs-18 lh-28 w-80 md-w-85">
                  Pour des travaux, le plus rapide reste de publier une demande : les pros de votre
                  quartier vous répondent directement.
                </span>{" "}
                <ArrowSwipe size={40} />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Avis + formulaire */}
      <section className={`${SECTION_X} py-0`} id="formulaire">
        <div className="container-fluid">
          <div className="row">
            <div className="col-xl-4 lg-mb-30px">
              <div className="bg-white border-radius-20px p-11 lg-p-6 h-100 d-inline-flex flex-column w-100">
                <Pill
                  className="align-self-start text-white bg-base-color mb-30px"
                  anime={fadeUp()}
                >
                  Avis de clients
                </Pill>{" "}
                {reviewers.length > 0 && (
                  <div
                    className="d-flex align-items-center mb-auto lg-mb-50px sm-mb-30px"
                    data-anime={fadeUp(100)}
                  >
                    <div className="jf-faces">
                      {reviewers.map((r) => (
                        <img
                          key={r.author}
                          src={r.author_photo}
                          alt={r.author}
                          width={56}
                          height={56}
                        />
                      ))}
                    </div>
                    <span className="fs-15 lh-20 ms-15px">
                      <span className="fw-600 text-dark-gray d-block">
                        {stats?.missions_done ?? reviews.length} missions notées
                      </span>
                      après intervention, par les clients eux-mêmes.
                    </span>
                  </div>
                )}
                <div className="w-100" data-anime={fadeUp(150)}>
                  <div
                    className="swiper magic-cursor drag-cursor"
                    data-slider-options='{ "slidesPerView": 1, "spaceBetween": 60, "loop": true, "parallax": true, "speed": 1200, "navigation": { "nextEl": ".slider-one-slide-next-2", "prevEl": ".slider-one-slide-prev-2" }, "autoplay": { "delay": 5000, "disableOnInteraction": false }, "keyboard": { "enabled": true, "onlyInViewport": true }, "effect": "slide" }'
                  >
                    <div className="swiper-wrapper testimonials-style-13">
                      {(reviews.length
                        ? reviews
                        : [
                            {
                              author: "Jeflink",
                              trade: "",
                              pro: "",
                              comment: "Les premiers avis arrivent bientôt.",
                            },
                          ]
                      ).map((r, i) => (
                        <div
                          key={i}
                          className="swiper-slide last-paragraph-no-margin"
                          data-swiper-parallax="700"
                        >
                          <span className="fs-14 fw-600 text-uppercase mb-10px d-block">
                            @{r.author}
                            {r.trade ? ` · ${r.trade}` : ""}
                          </span>{" "}
                          <h3 className="h6 ls-minus-1px mb-0">« {r.comment} »</h3>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="row" data-anime={fadeUp(300)}>
                  <div className="col-12">
                    <div className="separator-line-1px w-100 bg-dark-gray mt-30px mb-30px xs-mt-30px xs-mb-30px" />
                  </div>
                  <div className="col-auto xs-mb-30px">
                    <div className="d-flex">
                      <div
                        className="slider-one-slide-prev-2 swiper-button-prev slider-navigation-style-04 h-60px w-60px lg-h-50px lg-w-50px flex-shrink-0 bg-very-light-gray"
                        tabIndex={0}
                        role="button"
                        aria-label="Avis précédent"
                      >
                        <i className="bi bi-arrow-left-short fs-32" />
                      </div>
                      <div
                        className="slider-one-slide-next-2 swiper-button-next slider-navigation-style-04 h-60px w-60px lg-h-50px lg-w-50px flex-shrink-0 bg-very-light-gray"
                        tabIndex={0}
                        role="button"
                        aria-label="Avis suivant"
                      >
                        <i className="bi bi-arrow-right-short fs-32" />
                      </div>
                    </div>
                  </div>
                  <div className="col ps-0">
                    <div className="d-flex flex-nowrap align-items-center justify-content-end">
                      <h3 className="alt-font fw-700 ls-minus-1px mb-0 me-10px">
                        {formatRating(stats?.average_rating ?? null)}
                      </h3>
                      <div className="text-center">
                        <div className="bg-dark-gray text-white border-radius-30px ps-15px pe-15px fs-12 lh-30 mb-5px">
                          <i className="bi bi-star-fill" /> <i className="bi bi-star-fill" />{" "}
                          <i className="bi bi-star-fill" /> <i className="bi bi-star-fill" />{" "}
                          <i className="bi bi-star-fill" />
                        </div>{" "}
                        <span className="fs-10 lh-16 fw-600 d-block text-uppercase">
                          Avis Jeflink
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div className="col-xl-8">
              <div
                className="cover-background h-100 border-radius-20px"
                style={{ backgroundImage: `url('${opt(`${IMG}-services-title.jpg`)}')` }}
              >
                <div className="row row-cols-1 row-cols-lg-2 m-0 h-100 align-items-center">
                  <div
                    className="col text-center p-3 md-p-50px sm-pt-40px sm-pb-40px sm-ps-20px sm-pe-20px"
                    data-anime={childsUp(150)}
                  >
                    <div className="d-inline-flex align-items-center mb-15px">
                      <i className="bi bi-asterisk icon-small text-white me-10px" />{" "}
                      <span className="alt-font fs-20 text-white">Vous êtes artisan ?</span>
                    </div>{" "}
                    <h4 className="alt-font ls-minus-1px text-white text-shadow-large w-85 xxl-w-100 md-w-85 sm-w-100 me-auto ms-auto">
                      Rejoignez les pros Jeflink et recevez des demandes près de chez vous.
                    </h4>
                    <div className="bg-white w-370px xl-w-100 lg-w-350px xs-w-100 ps-5px border-radius-50px d-flex align-items-center mx-auto box-shadow-medium-bottom">
                      <img className="me-5px xs-h-70px" src={opt(`${IMG}-about-08.png`)} alt="" />{" "}
                      <a
                        href="/inscription?role=pro"
                        className="fs-22 xs-fs-20 fw-500 ls-minus-05px d-inline-block text-dark-gray-hover text-start"
                      >
                        Devenir pro !
                      </a>
                    </div>
                  </div>
                  <div className="col p-5 md-p-7 blur-box bg-dark-gray-transparent-medium">
                    <h4 className="alt-font text-white mb-25 md-mb-10" data-anime={fadeIn(150)}>
                      Écrivez-nous, nous vous répondons vite.
                    </h4>
                    {envoye ? (
                      <div className="alert alert-success mb-0" role="status">
                        Merci ! Votre message est bien arrivé. Nous vous répondons par email.
                      </div>
                    ) : (
                      <ActionForm
                        action="/act/contact"
                        className="contact-form-style-03"
                        labels={{ name: "Nom", email: "Email", message: "Message" }}
                      >
                        {erreur && (
                          <div className="alert alert-danger mb-25px" role="alert">
                            {erreur}
                          </div>
                        )}
                        <div className="row justify-content-center">
                          <div className="col-md-12 xs-mb-30px">
                            <div className="position-relative form-group mb-10px xs-mb-0">
                              <span className="form-icon">
                                <i className="feather icon-feather-user icon-extra-medium text-white" />
                              </span>{" "}
                              <input
                                className="ps-0 border-radius-0px border-color-transparent-white-very-light bg-transparent form-control placeholder-light"
                                type="text"
                                name="name"
                                placeholder="Votre nom*"
                                aria-label="Votre nom"
                                autoComplete="name"
                                required
                              />
                            </div>
                          </div>
                          <div className="col-md-12 xs-mb-30px">
                            <div className="position-relative form-group mb-10px xs-mb-0">
                              <span className="form-icon">
                                <i className="feather icon-feather-mail icon-extra-medium text-white" />
                              </span>{" "}
                              <input
                                className="ps-0 border-radius-0px border-color-transparent-white-very-light bg-transparent form-control placeholder-light"
                                type="email"
                                name="email"
                                placeholder="Votre email*"
                                aria-label="Votre email"
                                autoComplete="email"
                                required
                              />
                            </div>
                          </div>
                          <div className="col-12 mb-4 xs-mb-30px">
                            <div className="position-relative form-group form-textarea mb-0">
                              <textarea
                                className="ps-0 border-radius-0px border-color-transparent-white-very-light bg-transparent form-control placeholder-light"
                                name="message"
                                placeholder="Votre message*"
                                aria-label="Votre message"
                                rows={4}
                                required
                              />{" "}
                              <span className="form-icon">
                                <i className="feather icon-feather-message-circle icon-extra-medium text-white" />
                              </span>
                            </div>
                          </div>
                          <div className="col-12 text-center text-md-end mb-20px sm-mt-25px">
                            <SwitchSubmit
                              label="Envoyer"
                              icon="icon-feather-send"
                              className="btn-large btn-white btn-box-shadow btn-rounded btn-icon-left w-100"
                            />
                          </div>
                          <div className="col-12">
                            <p className="mb-0 fs-14 lh-22 text-white opacity-5 text-center text-md-start">
                              Vos coordonnées servent uniquement à vous répondre. Elles ne sont ni
                              revendues ni utilisées pour de la publicité.
                            </p>
                          </div>
                        </div>
                      </ActionForm>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Où nous trouver */}
      <section className={SECTION_X}>
        <div className="container-fluid">
          <div className="row">
            <div className="col-lg-5 md-mb-50px sm-mb-40px">
              <Pill
                className="align-self-start text-white bg-base-color mb-8 md-mb-20px"
                anime={fadeUp()}
              >
                Où nous intervenons
              </Pill>{" "}
              <h3
                className="alt-font fw-500 ls-minus-2px mb-0"
                style={PERSPECTIVE}
                data-anime={lines()}
              >
                À Dakar et en banlieue, quartier par quartier.
              </h3>
            </div>
            <div className="col-lg-7 col-xl-6 offset-xl-1">
              <div
                className="row"
                data-anime='{ "el": "childs", "translateX": [30, 0], "opacity": [0,1], "duration": 600, "delay":0, "staggervalue": 300, "easing": "easeOutQuad" }'
              >
                {PLACES.map((place, i) => (
                  <div
                    key={place.name}
                    className={`col-md-6 col-xxl-5${i === 0 ? " sm-mb-30px" : ""}`}
                  >
                    <span className="fs-22 mb-10px d-block fw-600 text-dark-gray">
                      {place.name}
                    </span>{" "}
                    <p className="w-70 xl-w-100 mb-10px lg-w-90 md-w-70">{place.text}</p>
                    <div className="separator-line-1px bg-black-transparent-light w-80 mt-20px mb-20px sm-w-100" />
                    <div className="d-block">
                      <span className="text-dark-gray fw-500">E :</span>{" "}
                      <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
                    </div>
                    <div className="d-block mb-10px">
                      <span className="text-dark-gray fw-500">H :</span> lun–sam, 8 h–20 h
                    </div>{" "}
                    <a
                      href={`https://www.google.com/maps/search/${encodeURIComponent(`${place.name}, Sénégal`)}`}
                      target="_blank"
                      rel="noreferrer"
                      className="fs-14 text-dark-gray text-uppercase fw-600"
                    >
                      <span>
                        <i className="feather icon-feather-map-pin fs-14 me-5px" />
                        Voir sur la carte
                      </span>
                    </a>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>
    </PageShell>
  );
}
