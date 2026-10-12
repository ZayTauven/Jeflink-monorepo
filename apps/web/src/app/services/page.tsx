import type { Metadata } from "next";

import {
  Asterisk,
  childsUp,
  fadeIn,
  fadeUp,
  lines,
  PERSPECTIVE,
  Pill,
  SECTION_X,
  SwitchLink,
} from "@/components/crafto";
import { PageShell } from "@/components/page-shell";
import { getTrades } from "@/lib/api";
import { formatXOF } from "@/lib/format";

export const metadata: Metadata = { title: "Comment ça marche" };

const IMG = "/crafto/images/demo-marketing-strategy";

const STEPS = [
  {
    icon: "bi-chat-text",
    kicker: "Étape 1 · La demande",
    title: "Décrivez le besoin en deux minutes.",
    text: "Choisissez le métier et le quartier, expliquez ce qui ne va pas, ajoutez un repère pour trouver la maison et la date qui vous arrange. Publier une demande est gratuit.",
    lists: [
      ["Métier et quartier", "Description libre", "Repère (« portail vert »)", "Date souhaitée"],
      [
        "Urgence signalée",
        "Gratuit, sans engagement",
        "Vue par les pros du quartier",
        "Annulable à tout moment",
      ],
    ],
    image: "/images/services/etape-1.webp",
    badge: ["2 min", "Pour publier"],
  },
  {
    icon: "bi-receipt",
    kicker: "Étape 2 · Les devis",
    title: "Comparez jusqu'à trois devis.",
    text: "Les pros vérifiés de votre métier vous répondent avec un montant en F CFA et ce qu'il comprend. Vous voyez leur note et leur expérience, puis vous choisissez.",
    lists: [
      ["Montant en F CFA", "Ce qui est compris", "Note des clients", "Années d'expérience"],
      ["Trois devis au plus", "Pas de surenchère", "Choix libre", "Les autres pros sont prévenus"],
    ],
    image: "/images/services/etape-2.webp",
    badge: ["3", "Devis au plus"],
  },
  {
    icon: "bi-patch-check",
    kicker: "Étape 3 · La mission",
    title: "Le pro vient, vous notez.",
    text: "Une fois le devis accepté, le pro est réservé et vous avez son numéro. Le travail fait, la mission est clôturée et votre avis aide les prochains clients.",
    lists: [
      ["Pro réservé", "Numéro partagé", "Historique daté", "Clôture de mission"],
      ["Note de 1 à 5", "Commentaire libre", "Avis vérifiés", "Recours auprès de Jeflink"],
    ],
    image: "/images/services/etape-3.webp",
    badge: ["100%", "Avis vérifiés"],
  },
];

const PRO_STEPS = [
  {
    icon: "line-icon-Idea-5",
    title: "Inscription et vérification",
    text: "Vos métiers, vos quartiers, puis un contrôle par l'équipe.",
  },
  {
    icon: "line-icon-Fountain-Pen",
    title: "Devis sur les demandes",
    text: "Vous chiffrez les demandes qui vous correspondent.",
  },
  {
    icon: "line-icon-Like-2",
    title: "Mission et avis",
    text: "Chaque mission réussie renforce votre réputation.",
  },
];

export default async function ServicesPage() {
  const trades = await getTrades();
  const marquee = trades.length
    ? trades.map((t) => t.name)
    : ["Plomberie", "Électricité", "Ménage"];

  return (
    <PageShell>
      {/* Titre de page */}
      <section className={`${SECTION_X} pt-0 md-pt-50px pb-0 top-space-margin`}>
        <div className="container-fluid">
          <div className="row">
            <div className="col-md-5 col-xl-4 sm-mb-30px">
              <div className="bg-white border-radius-20px p-14 sm-p-7 xl-p-12 h-100 d-flex flex-column align-items-start">
                <Pill className="text-white bg-base-color mb-auto" anime={fadeUp()}>
                  Comment ça marche
                </Pill>{" "}
                <h1
                  className="h3 alt-font fw-500 ls-minus-2px mb-0 mt-30 md-mt-0 pt-70px"
                  style={PERSPECTIVE}
                  data-anime={lines()}
                >
                  Simple pour vous, sérieux pour le pro.
                </h1>
              </div>
            </div>
            <div className="col-md-7 col-xl-8" data-anime={fadeIn(300)}>
              <img
                className="border-radius-20px object-fit-cover h-100"
                src="/images/services/titre.webp"
                alt=""
              />
            </div>
          </div>
        </div>
      </section>

      {/* Manifeste */}
      <section
        className={`${SECTION_X} cover-background`}
        style={{ backgroundImage: `url('${IMG}-lining-bg.jpg')` }}
      >
        <div className="container-fluid">
          <div className="row justify-content-center">
            <div
              className="col-xl-11 col-xxl-8 text-center position-relative"
              data-anime={fadeIn()}
            >
              <img
                src={`${IMG}-services-01.png`}
                className="position-absolute left-minus-50px bottom-0 d-none d-xl-block"
                data-bottom-top="transform: rotate(0deg) translateX(0px); filter: blur(-6px)"
                data-top-bottom="transform:rotate(10deg) translateX(50px); filter: blur(10px)"
                alt=""
              />{" "}
              <img
                src={`${IMG}-services-02.png`}
                className="position-absolute right-minus-100px top-20px d-none d-xl-block"
                data-bottom-top="transform: rotate(0deg) translateX(0px); filter: blur(-6px)"
                data-top-bottom="transform:rotate(-10deg) translateX(-30px); filter: blur(10px)"
                alt=""
              />{" "}
              <Asterisk className="mb-25px position-relative">
                Une demande, un pro, un avis
              </Asterisk>{" "}
              <h2 className="alt-font fw-500 ls-minus-2px position-relative m-0">
                De la fuite d&apos;eau au grand ménage, une seule façon de faire : claire, tracée,
                au prix convenu.
              </h2>
            </div>
          </div>
        </div>
      </section>

      {/* Les trois étapes, cartes empilées */}
      <section className={`${SECTION_X} big-section pt-0`}>
        <div className="container-fluid">
          <div
            className="stack-card cards"
            data-scale="true"
            data-top-space="40"
            data-top-padding="0"
          >
            {STEPS.map((step, i) => (
              <div
                key={step.title}
                className={`stack-item${i ? " mt-60px md-mt-50px sm-mt-40px" : ""}`}
                data-index={i}
              >
                <div className="stack-card-item bg-white box-shadow-double-large border-radius-20px overflow-hidden">
                  <div className="row justify-content-center flex-column-reverse flex-lg-row g-0">
                    <div className="col-lg-6 col-xxl-5 ps-6 lg-ps-5 sm-ps-7 md-pe-5 sm-pe-7 pt-6 pb-5 md-pt-50px md-pb-50px sm-pt-40px sm-pb-40px">
                      <div className="icon-with-text-style-08 mb-20px">
                        <div className="feature-box feature-box-left-icon-middle">
                          <div className="feature-box-icon feature-box-icon-rounded w-70px h-70px sm-w-55px sm-h-55px rounded-circle bg-base-transparent-extra-light me-10px text-center">
                            <i className={`bi ${step.icon} fs-22 text-base-color`} />
                          </div>
                          <div className="feature-box-content last-paragraph-no-margin">
                            <span className="alt-font fs-20">{step.kicker}</span>
                          </div>
                        </div>
                      </div>
                      <div className="alt-font fs-60 xl-fs-55 lg-fs-50 fw-500 ls-minus-2px w-80 xl-w-90 lg-w-95 md-w-100 mb-25px">
                        {step.title}
                      </div>
                      <div className="d-flex justify-content-between align-items-end me-50px md-me-0">
                        <p className="w-80 lg-w-90 mb-0">{step.text}</p>{" "}
                        <svg
                          width="21"
                          height="21"
                          viewBox="0 0 21 21"
                          fill="none"
                          aria-hidden="true"
                        >
                          <path
                            d="M1.5 1.5L19.5 19.5M1.5 19.5H19.5V1.5"
                            stroke="#F55608"
                            strokeWidth="3"
                            strokeLinecap="round"
                          />
                        </svg>
                      </div>
                      <div className="row g-0 border-top border-color-transparent-dark-very-light pt-60px mt-60px lg-pt-40px lg-mt-40px md-pt-30px md-mt-30px">
                        {step.lists.map((list, j) => (
                          <div key={j} className="col-md-6 col-xl-5 lg-pe-15px">
                            <ul className="p-0 m-0 list-style-02">
                              {list.map((item) => (
                                <li key={item} className="mb-5px">
                                  <span className="me-5px">+</span>
                                  {item}
                                </li>
                              ))}
                            </ul>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="col-lg-6 col-xxl-7 border-start md-border-start-0 border-color-transparent-dark-very-light p-6 md-p-0">
                      <figure className="position-relative mb-0">
                        <img className="border-radius-15px w-100" src={step.image} alt="" />{" "}
                        <figcaption
                          className={`position-absolute text-center${i === 0 ? " blur-box" : ""} border-radius-10px right-minus-50px md-right-30px md-top-30px sm-right-15px sm-top-15px top-minus-50px w-150px p-25px xxl-p-20px bg-base-color`}
                        >
                          <div className="fs-45 alt-font fw-600 ls-minus-2px text-white mb-5px mt-5px">
                            {step.badge[0]}
                          </div>{" "}
                          <span className="fs-20 lh-20 text-white d-block mb-15px">
                            {step.badge[1]}
                          </span>
                        </figcaption>
                      </figure>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Les métiers */}
      <section className={`${SECTION_X} pt-0 overflow-x-clip`}>
        <div className="container-fluid">
          <div className="row justify-content-between">
            <div className="col-lg-5 col-xxl-4 position-relative z-index-1 md-mb-50px sm-mb-40px">
              <div className="position-sticky top-50px" data-anime={childsUp()}>
                <Pill
                  className="text-dark-gray border border-color-transparent-dark-light mb-auto mb-20px"
                  anime={fadeUp()}
                >
                  Nos métiers
                </Pill>{" "}
                <h2
                  className="alt-font ls-minus-2px fw-500"
                  style={PERSPECTIVE}
                  data-anime={lines()}
                >
                  Six métiers pour commencer, d&apos;autres arrivent.
                </h2>
                <p className="w-80 lg-w-100 mb-30px" data-anime={fadeUp(1200)}>
                  Les besoins les plus fréquents de la maison, avec des pros vérifiés dans chacun.
                  Vitrier, jardinier, serrurier… le catalogue s&apos;agrandit au fil des
                  recrutements.
                </p>{" "}
                <SwitchLink
                  href="/espace/demandes/nouvelle"
                  label="Faire une demande"
                  icon="icon-feather-edit"
                  className="btn-extra-large btn-dark-gray btn-rounded btn-box-shadow"
                />
              </div>
            </div>
            <div className="col-lg-7 col-xxl-6 position-relative">
              <img
                src={`${IMG}-services-09.jpg`}
                className="position-absolute bottom-150px left-minus-40px"
                data-bottom-top="transform: translateY(100px)"
                data-top-bottom="transform: translateY(-100px)"
                alt=""
              />{" "}
              <img
                src={`${IMG}-services-10.jpg`}
                className="position-absolute top-150px right-minus-80px mt-70px"
                data-bottom-top="transform: translateY(-100px)"
                data-top-bottom="transform: translateY(100px)"
                alt=""
              />{" "}
              <div className="row row-cols-1 row-cols-md-2" data-anime={childsUp()}>
                {trades.map((trade, i) => (
                  <div
                    key={trade.slug}
                    className={`col clients-style-07${i < trades.length - 2 ? " mb-30px" : i === trades.length - 2 ? " sm-mb-30px" : ""}`}
                  >
                    <div className="d-flex align-items-center justify-content-center overflow-hidden border-radius-20px position-relative client-box bg-white-transparent-medium blur-box min-h-300px">
                      <div className="text-center">
                        <i
                          className={`bi ${trade.icon} icon-double-large text-base-color d-block mb-10px`}
                        />
                        <span className="alt-font fs-24 fw-500 text-dark-gray">{trade.name}</span>
                      </div>{" "}
                      <div className="client-info light-hover">
                        <div className="d-flex align-items-center justify-content-center client-content border-radius-20px bg-white-transparent w-60px h-60px">
                          <div className="client-icon">
                            <span className="icon-very-medium">+</span>
                          </div>
                          <div className="d-flex flex-column align-items-center justify-content-center client-link p-10 text-center last-paragraph-no-margin">
                            <a href={`/metiers/${trade.slug}`} className="alt-font fs-22 fw-500">
                              {trade.name}
                            </a>{" "}
                            <p className="w-85 lg-w-100 mt-15px">
                              {trade.tagline}
                              {trade.starting_price ? (
                                <>
                                  <br />À partir de {formatXOF(trade.starting_price)}
                                </>
                              ) : null}
                            </p>
                          </div>
                          <div className="box-overlay bg-white" />
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Le parcours côté pro */}
      <section className={`${SECTION_X} pt-0 pb-0`}>
        <div className="container-fluid">
          <div className="row">
            <div className="col-lg-5 col-xl-4 md-mb-30px">
              <div
                className="cover-background p-15 xl-p-12 md-p-8 border-radius-20px overflow-hidden d-flex flex-column align-items-start h-100 md-h-700px sm-h-500px"
                style={{ backgroundImage: "url('/images/services/pros.webp')" }}
              >
                <Pill className="text-white bg-base-color mb-auto" anime={fadeUp()}>
                  Pour les pros
                </Pill>{" "}
                <h3
                  className="alt-font fw-500 text-white ls-minus-2px sm-ls-minus-1px mb-0 md-w-70 sm-w-100"
                  style={PERSPECTIVE}
                  data-anime={lines()}
                >
                  Le parcours côté artisan.
                </h3>
              </div>
            </div>
            <div className="col-lg-7 col-xl-8">
              <div
                className="cover-background ps-8 pe-8 xl-ps-6 xl-pe-6 pt-10 pb-10 border-radius-20px overflow-hidden h-100"
                style={{ backgroundImage: `url('${IMG}-services-07.jpg')` }}
              >
                <div className="row justify-content-center mt-20px">
                  <div className="col-12 text-center">
                    <h3 className="alt-font text-white fw-500 ls-minus-1px z-index-1 position-relative">
                      Trois étapes
                    </h3>
                  </div>
                </div>
                <div
                  className="row row-cols-1 row-cols-lg-3 row-cols-sm-2 mt-7 md-mt-50px sm-mt-30px"
                  data-anime='{ "el": "childs", "translateX": [-50, 0], "opacity": [0,1], "duration": 600, "delay": 0, "staggervalue": 100, "easing": "easeOutQuad" }'
                >
                  {PRO_STEPS.map((s, i) => (
                    <div
                      key={s.title}
                      className={`col text-center process-step-style-02 hover-box last-paragraph-no-margin${i < 2 ? " md-mb-50px sm-mb-40px" : ""}`}
                    >
                      <i className={`${s.icon} text-base-color icon-double-large mb-30px`} />{" "}
                      <span className="alt-font fs-20 xl-fs-18 d-block text-white mb-10px">
                        {s.title}
                      </span>{" "}
                      <p className="text-white opacity-5 d-inline-block w-80 xl-w-100">{s.text}</p>{" "}
                      <div className="process-step-icon-box position-relative mt-35px">
                        {i < 2 && (
                          <span className="progress-step-separator bg-white opacity-2 w-55 separator-line-1px" />
                        )}
                        <div className="process-step-icon d-flex justify-content-center align-items-center mx-auto bg-white h-80px w-80px alt-font fs-22 fw-500 rounded-circle box-shadow-double-large">
                          <span className="number position-relative z-index-1 fw-500">
                            0{i + 1}
                          </span>{" "}
                          <div className="box-overlay bg-white rounded-circle" />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <div
                  className="position-absolute top-60px xl-top-40px sm-top-30px ls-minus-6px left-0px w-100 text-center"
                  data-bottom-top="transform: translate3d(280px, 0px, 0px);"
                  data-top-bottom="transform: translate3d(-180px, 0px, 0px);"
                >
                  <div className="alt-font fs-170 lg-fs-140 xs-fs-110 fw-700 opacity-8 text-white-space-nowrap">
                    savoir-faire
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Bandeau défilant */}
      <section className="py-0 position-relative" data-anime={fadeIn()}>
        <div className="text-center">
          <img className="md-h-400px sm-h-350px" src={`${IMG}-portfolio-07.jpg`} alt="" />
        </div>
        <div className="container-fluid absolute-middle-left">
          <div className="row position-relative">
            <div
              className="col swiper swiper-width-auto text-center"
              data-slider-options='{ "slidesPerView": "auto", "spaceBetween":40, "centeredSlides": true, "speed": 8000, "loop": true, "allowTouchMove": false, "autoplay": { "delay":1, "disableOnInteraction": false }, "keyboard": { "enabled": true, "onlyInViewport": true }, "breakpoints": { "1400": { "spaceBetween":120 }, "1200": { "spaceBetween":80 }, "768": { "spaceBetween":60 } }, "effect": "slide" }'
            >
              <div className="swiper-wrapper marquee-slide">
                {[...marquee, ...marquee].flatMap((name, i) => [
                  <div key={`t${i}`} className="swiper-slide text-white-space-nowrap">
                    <div className="fs-150 lg-fs-110 sm-fs-90 lg-lh-normal xl-fs-130 alt-font ls-minus-5px">
                      {name}
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
    </PageShell>
  );
}
