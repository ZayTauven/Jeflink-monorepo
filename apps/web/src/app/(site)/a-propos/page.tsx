import type { Metadata } from "next";

import {
  ArrowSwipe,
  Asterisk,
  childsFade,
  childsUp,
  fadeIn,
  fadeUp,
  lines,
  PERSPECTIVE,
  Pill,
  SECTION_X, opt } from "@/components/crafto";
import { MarqueePause } from "@/components/marquee-pause";
import { PageShell } from "@/components/page-shell";
import { RotatingText } from "@/components/rotating-text";
import { getStats } from "@/lib/api";

export const metadata: Metadata = { title: "À propos" };

const IMG = "/crafto/images/demo-marketing-strategy";

const REASONS = [
  {
    icon: opt(`${IMG}-about-icon-01.png`),
    title: "Des pros vérifiés",
    text: "Identité, téléphone et références contrôlés par l'équipe Jeflink avant la première mission.",
  },
  {
    icon: opt(`${IMG}-about-icon-02.png`),
    title: "Des devis comparables",
    text: "Trois devis au plus, en F CFA, avec ce qu'ils comprennent. Vous choisissez en connaissance de cause.",
  },
  {
    icon: opt(`${IMG}-about-icon-03.png`),
    title: "Une adresse par repères",
    text: "« Derrière la mosquée, portail vert » : le pro sait où venir, comme on se repère vraiment à Dakar.",
  },
  {
    icon: opt(`${IMG}-about-icon-04.png`),
    title: "Des avis qui comptent",
    text: "Seul un client dont la mission est terminée peut noter le pro. Pas d'avis inventés.",
  },
];

const MARQUEE = ["Le bon pro", "Au bon prix", "Travail garanti", "Dakar et banlieue"];

export default async function AboutPage() {
  const stats = await getStats();
  const counters = [
    { label: "Pros vérifiés sur la plateforme.", value: stats?.pros ?? 0 },
    { label: "Missions terminées et notées.", value: stats?.missions_done ?? 0 },
    { label: "Quartiers desservis à Dakar et en banlieue.", value: stats?.zones ?? 0 },
    { label: "Métiers disponibles aujourd'hui.", value: stats?.trades ?? 0 },
  ];

  return (
    <PageShell>
      {/* Titre de page */}
      <section className={`${SECTION_X} pt-0 md-pt-50px pb-0 top-space-margin`}>
        <div className="container-fluid">
          <div className="row">
            <div className="col-md-5 col-xl-4 sm-mb-30px">
              <div className="bg-white border-radius-20px p-14 sm-p-7 xl-p-12 h-100 d-flex flex-column align-items-start">
                <Pill className="text-white bg-base-color mb-auto" anime={fadeUp()}>
                  À propos de Jeflink
                </Pill>{" "}
                <h1
                  className="h3 alt-font fw-500 ls-minus-2px mb-0 mt-30 md-mt-0 pt-70px"
                  style={PERSPECTIVE}
                  data-anime={lines()}
                >
                  Votre maison, des pros vérifiés.
                </h1>
              </div>
            </div>
            <div className="col-md-7 col-xl-8" data-anime={fadeIn(300)}>
              <div className="h-100 d-flex">
                <img
                  className="border-radius-20px object-fit-cover"
                  src="/images/a-propos/titre.webp"
                  alt=""
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Logos (template) */}
      <section className={`${SECTION_X} py-0`}>
        <div className="container-fluid">
          <div
            className="row row-cols-2 row-cols-lg-6 row-cols-md-3 row-cols-sm-3 clients-style-05 m-0 pt-60px pb-60px md-pt-50px md-pb-50px text-center justify-content-center border-bottom border-color-transparent-dark-light"
            data-anime='{ "el": "childs", "scale": [0,1], "opacity": [0,1], "duration": 300, "delay": 0, "staggervalue": 200, "easing": "easeOutQuad" }'
          >
            {[1, 2, 3, 4, 5, 6].map((n) => (
              <div
                key={n}
                className={`col${n <= 3 ? " md-mb-40px" : n === 4 ? " xs-mb-40px" : ""}`}
              >
                <div className="client-box">
                  <img
                    src={`/crafto/images/demo-branding-studio-client-0${n}.svg`}
                    className="h-25px"
                    alt=""
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Mission et vision */}
      <section className={SECTION_X}>
        <div className="container-fluid">
          <div className="row">
            <div className="col-lg-5 col-xl-6 text-center md-mb-50px" data-anime={childsFade()}>
              <div className="position-relative d-inline-block">
                <img className="animation-float" src={opt(`${IMG}-about-01.jpg`)} alt="" />{" "}
                <div className="bg-white-transparent-extra-light blur-box box-shadow-medium-bottom border-radius-100 border border-color-white position-absolute right-minus-40px xl-right-minus-0px sm-right-20px lg-right-0px top-40px d-flex flex-column align-items-center justify-content-center lg-w-160px md-w-140px">
                  <div className="w-130px h-130px lg-w-100px lg-h-100px md-w-90px md-h-90px box-shadow-medium-bottom position-absolute bg-white-transparent-extra-light blur-box border-radius-100 border border-color-white d-flex align-items-center justify-content-center">
                    <img src={opt(`${IMG}-09.png`)} alt="" />
                  </div>{" "}
                  <RotatingText id="a-propos" className="animation-rotation" />
                </div>
              </div>
            </div>
            <div className="col-lg-7 col-xl-6">
              <div
                className="feature-box feature-box-left-icon-middle last-paragraph-no-margin mb-25px"
                data-anime={fadeUp()}
              >
                <div className="feature-box-icon me-10px">
                  <i className="bi bi-asterisk icon-extra-medium text-base-color" />
                </div>
                <div className="feature-box-content">
                  <span className="alt-font fs-22 sm-fs-20">Pourquoi Jeflink</span>
                </div>
              </div>
              <h2
                className="alt-font ls-minus-1px mb-0 fw-500 md-w-85 xs-w-100"
                style={PERSPECTIVE}
                data-anime={lines()}
              >
                Faire venir un pro chez soi devrait être simple et sûr.
              </h2>
              <div className="d-flex align-items-center justify-content-between border-top border-color-dark-gray mt-15 xs-mt-30px md-mt-40px pt-40px xs-pt-30px">
                <div className="row row-cols-1 row-cols-sm-2" data-anime={childsUp()}>
                  <div className="col xs-mb-30px">
                    <span className="fs-18 fw-500 d-block mb-10px">Notre mission</span>{" "}
                    <p className="mb-0 w-85 xl-w-100">
                      Donner à chaque foyer de Dakar un accès simple à des artisans fiables, avec un
                      prix clair avant l&apos;intervention.
                    </p>
                  </div>
                  <div className="col">
                    <span className="fs-18 fw-500 d-block mb-10px">Notre vision</span>{" "}
                    <p className="mb-0 w-85 xl-w-100">
                      Que les bons artisans vivent mieux de leur métier, portés par leur réputation
                      et pas seulement par le bouche-à-oreille.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Pour les pros */}
      <section className={`${SECTION_X} pt-0 pb-0`}>
        <div className="container-fluid">
          <div className="row">
            <div
              className="col-sm-6 col-lg-4 xs-mb-30px"
              data-anime='{ "translateX": [50, 0], "opacity": [0,1], "duration": 600, "delay":0, "staggervalue": 150, "easing": "easeOutQuad" }'
            >
              <div
                className="cover-background border-radius-20px h-700px sm-h-400px lg-h-500px"
                style={{ backgroundImage: "url('/images/a-propos/pros.webp')" }}
              />
            </div>
            <div className="col-md-12 col-lg-4 md-order-minus-1 md-mb-30px">
              <div
                className="bg-white border-radius-20px p-14 md-p-7 xxl-p-10 h-100 d-flex flex-column align-items-start h-100 position-relative"
                data-anime={childsUp()}
              >
                <div className="fs-12 lh-18 fw-500 text-uppercase text-white bg-base-color border-radius-50px ps-20px pe-20px pt-10px pb-10px mb-auto md-mb-15 d-inline-block">
                  Pour les pros
                </div>{" "}
                <h3 className="alt-font fw-500 ls-minus-1px lg-fs-40 mb-15px">
                  Plus de clients, moins de paperasse.
                </h3>
                <p className="w-90 lg-w-100 mb-30px">
                  Jeflink apporte aux artisans des demandes de leur quartier, dans leurs métiers.
                  Ils chiffrent, se déplacent, et leur réputation grandit avec chaque avis.
                </p>
                <div className="progress-bar-style-02 w-100">
                  <div className="progress mb-15px border-radius-50px fw-600 fs-12 lh-12 text-white bg-white">
                    <div
                      className="progress-bar bg-gradient-orange-transparent m-0"
                      role="progressbar"
                      aria-valuenow={100}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label="Avis issus de missions terminées"
                    >
                      <span className="progress-bar-percent text-orange fw-600">100%</span>
                    </div>
                    <div className="progress-bar-title text-uppercase">Avis après mission</div>
                  </div>
                  <div className="progress border-radius-50px fw-600 fs-12 lh-12 text-white bg-white">
                    <div
                      className="progress-bar bg-gradient-blue-transparent m-0"
                      role="progressbar"
                      aria-valuenow={100}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label="Prix écrits dans le devis"
                    >
                      <span className="progress-bar-percent text-tropical-blue fw-600">100%</span>
                    </div>
                    <div className="progress-bar-title text-uppercase">
                      Prix écrit dans le devis
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div
              className="col-sm-6 col-lg-4"
              data-anime='{ "translateX": [-50, 0], "opacity": [0,1], "duration": 600, "delay":0, "staggervalue": 150, "easing": "easeOutQuad" }'
            >
              <div
                className="cover-background p-11 border-radius-20px overflow-hidden d-flex flex-column align-items-start h-700px sm-h-400px lg-h-500px"
                style={{ backgroundImage: `url('${opt(`${IMG}-about-03.jpg`)}')` }}
              >
                <a
                  href="/inscription?role=pro"
                  aria-label="Devenir pro Jeflink"
                  className="position-relative d-inline-block text-center rounded-circle video-icon-box video-icon-large mb-auto"
                >
                  <span>
                    <span className="video-icon bg-white">
                      <i className="fa-solid fa-play" />{" "}
                      <span className="video-icon-sonar">
                        <span className="video-icon-sonar-bfr bg-white opacity-9" />
                      </span>
                    </span>
                  </span>
                </a>{" "}
                <h3 className="h6 alt-font text-white fw-400 mb-0">
                  Vous êtes artisan ? Rejoignez Jeflink en quelques minutes.
                </h3>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Bandeau défilant */}
      <section className="pb-4 pt-4 position-relative">
        <div className="text-center">
          <img
            className="animation-float md-h-350px sm-h-250px"
            src={opt(`${IMG}-about-04.jpg`)}
            alt=""
          />
        </div>
        <div className="container-fluid absolute-middle-left">
          <div className="row position-relative">
              <MarqueePause />
            <div
              className="col swiper swiper-width-auto text-center"
              data-slider-options='{ "slidesPerView": "auto", "spaceBetween":40, "centeredSlides": true, "speed": 8000, "loop": true, "allowTouchMove": false, "autoplay": { "delay":1, "disableOnInteraction": false }, "keyboard": { "enabled": true, "onlyInViewport": true }, "breakpoints": { "1400": { "spaceBetween":120 }, "1200": { "spaceBetween":80 }, "768": { "spaceBetween":60 } }, "effect": "slide" }'
            >
              <div className="swiper-wrapper marquee-slide">
                {[...MARQUEE, ...MARQUEE].flatMap((text, i) => [
                  <div key={`t${i}`} className="swiper-slide text-white-space-nowrap">
                    <div className="fs-150 lg-fs-110 sm-fs-90 lg-lh-normal xl-fs-130 alt-font ls-minus-5px">
                      {text}
                    </div>
                  </div>,
                  <div key={`s${i}`} className="swiper-slide text-white-space-nowrap">
                    <span className="fs-170 xl-fs-140 sm-fs-100 alt-font ls-minus-5px d-inline-block align-middle">
                      ✧
                    </span>
                  </div>,
                ])}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Ce qui fait la différence */}
      <section className={`${SECTION_X} pt-0`}>
        <div className="container-fluid">
          <div className="row">
            <div className="col-lg-5 md-mb-50px sm-mb-40px">
              <div className="position-sticky top-50px last-paragraph-no-margin">
                <Pill className="text-white bg-base-color mb-25px" anime={fadeUp()}>
                  100 % pros vérifiés
                </Pill>{" "}
                <h2
                  className="alt-font ls-minus-2px fw-500"
                  style={PERSPECTIVE}
                  data-anime={lines()}
                >
                  Ce qui fait la différence.
                </h2>
                <p className="w-80 xl-w-100" data-anime={fadeUp(1200)}>
                  Le pro qui ne vient pas, le prix qui change sur place, le travail bâclé : à Dakar,
                  ce sont les trois raisons d&apos;hésiter. Jeflink répond à chacune par une règle
                  appliquée, pas par une promesse.
                </p>
              </div>
            </div>
            <div className="col-lg-7 col-xl-6 offset-xl-1">
              <div
                className="row row-cols-1 row-cols-sm-2"
                data-anime='{ "el": "childs", "perspective": [1200,1200], "scale": [1.2, 1], "rotateX": [50, 0], "opacity": [0,1], "duration": 600, "delay": 0, "staggervalue": 300, "easing": "easeOutQuad" }'
              >
                {REASONS.map((r, i) => (
                  <div
                    key={r.title}
                    className={`col icon-with-text-style-07 transition-inner-all${i < 2 ? " mb-30px" : i === 2 ? " xs-mb-30px" : ""}`}
                  >
                    <div className="bg-white feature-box h-100 justify-content-start box-shadow-quadruple-large-hover text-start p-14 xs-p-9 md-p-11 border-radius-10px">
                      <div className="feature-box-icon mb-30 lg-mb-20">
                        <img src={r.icon} alt="" />
                      </div>
                      <div className="feature-box-content mt-10">
                        <span className="fs-20 ls-minus-05px fw-500 d-block mb-10px">
                          {r.title}
                        </span>{" "}
                        <p className="mb-0">{r.text}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="hover-arrow-swipe d-flex align-items-center justify-content-between border-top border-color-dark-gray pt-30px mt-50px sm-mt-40px">
                <span className="fs-20 sm-fs-18 lh-28 w-85 sm-w-80">
                  Nous voulons que chaque mission se passe assez bien pour que vous rappeliez le
                  même pro, par Jeflink.
                </span>{" "}
                <ArrowSwipe size={40} />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Galerie */}
      <section className="overflow-hidden pt-0">
        <div className="container-fluid p-0">
          <div className="row align-items-center g-0">
            <div
              className="col-12"
              data-anime='{ "opacity": [0,1], "duration": 1200, "delay": 0, "staggervalue": 150, "easing": "easeOutQuad" }'
            >
              <div className="outside-box-right-2 outside-box-left-2">
                <div
                  className="swiper swiper-width-auto magic-cursor drag-cursor"
                  data-slider-options='{ "slidesPerView": "auto", "spaceBetween": 20, "loop": true, "autoplay": { "delay": 3000, "disableOnInteraction": false }, "keyboard": { "enabled": true, "onlyInViewport": true }, "effect": "slide" }'
                >
                  <div className="swiper-wrapper">
                    {[1, 2, 3, 4, 5, 6].map((n, i) => (
                      <div key={i} className="swiper-slide">
                        <img
                          src={`/images/a-propos/galerie-${n}.webp`}
                          className="border-radius-10px md-h-400px sm-h-250px"
                          alt=""
                        />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Compteurs (données réelles de la plateforme) */}
      <section className={`${SECTION_X} pt-0 pb-0`}>
        <div className="container-fluid">
          <div className="row g-0 counter-style-04" data-anime={childsUp()}>
            {counters.map((c, i) => (
              <div
                key={c.label}
                className={`col-lg-3 col-sm-6 feature-box text-start border-start xs-border border-color-transparent-dark-light${i % 2 ? " md-border-end" : ""} ps-35px pe-35px lg-ps-25px lg-pe-25px${i === 0 ? " md-ps-35px md-pe-35px" : ""} sm-p-30px${i < 2 ? " md-mb-50px sm-mb-30px" : i === 2 ? " xs-mb-30px" : ""}`}
              >
                <div className="feature-box-content">
                  <p className="fs-20 sm-fs-18 mb-10 sm-mb-10 w-70 xxl-w-100 md-w-80 sm-w-100">
                    {c.label}
                  </p>{" "}
                  <h2
                    className="vertical-counter d-inline-flex alt-font fw-500 ls-minus-2px mt-20 mb-0"
                    data-text=""
                    data-to={c.value}
                  >
                    <sup className="top-0">
                      <i className="bi bi-arrow-up text-base-color icon-extra-medium" />
                    </sup>
                  </h2>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Appel aux pros */}
      <section
        className={`extra-big-section ${SECTION_X} cover-background`}
        style={{ backgroundImage: `url('${opt(`${IMG}-lining-bg.jpg`)}')` }}
      >
        <div className="container-fluid">
          <div className="row justify-content-center">
            <div className="col-lg-11 col-xxl-8 text-center" data-anime={childsUp()}>
              <Asterisk className="mb-25px">Rejoindre le réseau</Asterisk>{" "}
              <h2 className="alt-font fw-500 ls-minus-2px">
                Artisan ou technicien ? Faites grandir votre activité avec Jeflink.
              </h2>
              <p className="fs-18 w-65 md-w-100 lg-w-80 mx-auto mb-40px">
                Créez votre profil, choisissez vos métiers et vos quartiers. Après vérification par
                notre équipe, vous recevez les demandes qui vous correspondent.
              </p>
              <div className="bg-white w-370px sm-w-300px ps-5px border-radius-50px d-flex align-items-center mx-auto box-shadow-medium-bottom">
                <img className="me-5px sm-w-140px" src="/images/a-propos/avatars.webp" width={171} alt="" />{" "}
                <a
                  href="/inscription?role=pro"
                  className="fs-22 sm-fs-18 fw-500 ls-minus-05px d-inline-block text-dark-gray-hover"
                >
                  Devenir pro !
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>
    </PageShell>
  );
}
