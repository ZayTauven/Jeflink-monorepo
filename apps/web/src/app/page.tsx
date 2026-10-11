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
  SECTION_X,
  slideX,
  SwitchLink,
} from "@/components/crafto";
import { PageShell } from "@/components/page-shell";
import { getPros, getStats, getTrades } from "@/lib/api";
import { formatRating } from "@/lib/format";

const IMG = "/crafto/images/demo-marketing-strategy";

const PROMISES = [
  {
    tags: ["Vérifié", "Noté", "Proche"],
    title: "Le bon pro, près de chez vous.",
    text: "Chaque pro est contrôlé par l'équipe Jeflink avant sa première mission, puis noté par ses clients après chacune.",
    image: `${IMG}-03.jpg`,
  },
  {
    tags: ["Devis", "F CFA", "Sans surprise"],
    title: "Au bon prix, fixé avant de commencer.",
    text: "Jusqu'à trois devis par demande, en francs CFA, à comparer tranquillement. Le prix ne change pas sur place.",
    image: `${IMG}-04.jpg`,
  },
  {
    tags: ["Suivi", "Avis", "Recours"],
    title: "Travail garanti, du devis à l'avis.",
    text: "Chaque étape est tracée dans votre espace. Un souci après l'intervention ? L'équipe Jeflink fait le lien avec le pro.",
    image: `${IMG}-05.jpg`,
  },
];

const STEPS = [
  {
    kicker: "Votre demande",
    title: "Décrivez votre besoin.",
    text: "Le métier, le quartier, ce qui ne va pas, un repère pour trouver la maison. Deux minutes suffisent, et c'est gratuit.",
    cta: {
      href: "/espace/demandes/nouvelle",
      label: "Faire une demande",
      icon: "icon-feather-edit",
    },
  },
  {
    kicker: "Les devis",
    title: "Recevez jusqu'à 3 devis.",
    text: "Les pros vérifiés de votre quartier vous répondent avec un prix en F CFA et ce qu'il comprend. Vous comparez la note, l'expérience et le montant.",
    cta: { href: "/metiers", label: "Voir les métiers", icon: "icon-feather-grid" },
  },
  {
    kicker: "La mission",
    title: "Choisissez, puis notez.",
    text: "Vous acceptez un devis : le pro est réservé et vous avez son numéro. Une fois le travail fait, votre avis aide les prochains clients.",
    cta: { href: "/services", label: "Tout le parcours", icon: "icon-feather-layers" },
  },
];

const PLEDGES = [
  ["01", "Identité et savoir-faire", "vérifiés", "Pros"],
  ["02", "Prix en F CFA, écrit", "dans le devis", "Devis"],
  ["03", "Trois devis au plus,", "pas de surenchère", "Choix"],
  ["04", "Numéros échangés", "après réservation", "Vie privée"],
  ["05", "Avis possibles seulement", "après la mission", "Avis"],
];

const FAQ = [
  {
    q: "Combien coûte une demande ?",
    a: "Publier une demande est gratuit. Vous payez seulement le pro que vous choisissez, au prix écrit dans son devis.",
  },
  {
    q: "Comment les pros sont-ils vérifiés ?",
    a: "Avant sa première mission, chaque pro est contrôlé par l'équipe Jeflink : identité, téléphone et références. Ensuite, ce sont les avis des clients qui comptent.",
  },
  {
    q: "Dans quels quartiers intervenez-vous ?",
    a: "Dakar et sa banlieue : Ouakam, Mermoz, Liberté, Parcelles Assainies, Pikine, Guédiawaye, Keur Massar… La liste s'allonge à mesure que des pros nous rejoignent.",
  },
  {
    q: "Comment je paie le pro ?",
    a: "Pour l'instant, vous réglez le pro directement, en espèces ou par mobile money, au montant du devis accepté. Le paiement dans l'application arrivera plus tard.",
  },
];

export default async function HomePage() {
  const [stats, trades, pros] = await Promise.all([getStats(), getTrades(), getPros()]);
  const team = pros.filter((p) => p.photo).slice(0, 2);
  const marquee = trades.length
    ? trades.map((t) => t.name)
    : ["Plomberie", "Électricité", "Ménage"];

  return (
    <PageShell home>
      {/* Accroche */}
      <section
        className={`ipad-top-space-margin pt-15 sm-pt-50px md-pt-15 lg-pt-25 xl-pt-20 ${SECTION_X} pb-50px bg-gradient-top-green position-relative overflow-hidden`}
      >
        <div className="container-fluid">
          <div className="row">
            <div
              className="absolute-top-center top-0 h-100 z-index-0 d-flex align-items-center justify-content-center p-0"
              data-anime={fadeIn()}
            >
              <img
                className="html-video z-index-1 h-100"
                src={`${IMG}-hero-video-bg.jpg`}
                alt=""
              />
            </div>
            <div className="col-md-7 col-xl-8 position-relative z-index-1 sm-mb-30px">
              <h1
                className="fs-150 lg-fs-75 xl-fs-100 xxl-fs-120 alt-font ls-minus-5px sm-ls-minus-3px mb-0"
                style={PERSPECTIVE}
                data-anime={lines(200, 150)}
              >
                Le bon pro, au bon prix.
              </h1>
            </div>
            <div
              className="col-md-5 col-xl-4 ps-12 md-ps-15px lg-ps-9 xl-ps-15px xxl-ps-5 position-relative z-index-1"
              data-anime={childsUp(600)}
            >
              <div className="d-flex align-items-center mb-20px pb-20px border-bottom border-color-dark-gray">
                <img className="me-15px md-w-50px" src={`${IMG}-hero-02.png`} alt="" />
                <h2 className="alt-font fw-600 ls-minus-2px mb-0 flex-shrink-0 me-15px">
                  {stats?.average_rating ? `${formatRating(stats.average_rating)}/5` : "3 devis"}
                </h2>
                <span className="fs-18 lh-22 alt-font">
                  {stats?.average_rating ? "Note moyenne des clients" : "au plus par demande"}
                </span>
              </div>
              <p>
                Plombiers, électriciens, frigoristes, équipes de ménage : des pros vérifiés à Dakar,
                avec un devis clair avant chaque intervention.
              </p>
              <SwitchLink
                href="/espace/demandes/nouvelle"
                label="Faire une demande"
                icon="icon-feather-edit"
                className="btn-large btn-base-color btn-rounded btn-box-shadow fw-400"
              />
            </div>
          </div>
          <div
            className="row align-items-center justify-content-center justify-content-md-between g-0 position-relative z-index-1 border-top border-color-dark-gray mt-60px pt-60px sm-mt-40px sm-pt-40px"
            data-anime={fadeUp(1800)}
          >
            <div className="col-sm-8 col-md-7 col-lg-6 col-xl-5 col-xxl-4 sm-mb-30px">
              <div className="hover-arrow-swipe d-flex align-items-center w-80 xxl-w-100 last-paragraph-no-margin">
                <ArrowSwipe
                  size={71}
                  className="me-30px md-me-20px"
                  svgClassName="md-w-50px md-h-50px sm-w-40px sm-h-40px"
                />
                <div className="fs-24 sm-fs-22 d-inline-block">
                  Dakar et banlieue — {stats?.zones ?? 22} quartiers desservis
                </div>
              </div>
            </div>
            <div className="col-md-5 col-xl-4 col-xxl-3 d-flex justify-content-center">
              <img className="me-15px ms-15px md-w-110px" src={`${IMG}-rating-01.png`} alt="" />
              <img className="me-15px ms-15px md-w-110px" src={`${IMG}-rating-02.png`} alt="" />
            </div>
          </div>
        </div>
      </section>

      {/* Comment ça marche, en bref */}
      <section className={`${SECTION_X} pt-0`}>
        <div className="container-fluid">
          <div className="row">
            <div className="col-md-5 col-xl-4 sm-mb-30px" data-anime={slideX(-30)}>
              <div
                className="cover-background p-10 sm-p-7 border-radius-20px overflow-hidden d-flex flex-column align-items-start h-100 sm-h-400px"
                style={{ backgroundImage: `url('${IMG}-01.jpg')` }}
              >
                <a
                  href="/services"
                  aria-label="Voir comment ça marche"
                  className="position-relative d-inline-block text-center rounded-circle video-icon-box video-icon-large mb-auto"
                >
                  <span>
                    <span className="video-icon bg-white">
                      <i className="fa-solid fa-play text-dark-gray" />
                      <span className="video-icon-sonar">
                        <span className="video-icon-sonar-bfr bg-white opacity-9" />
                      </span>
                    </span>
                  </span>
                </a>
                <h3 className="h6 alt-font text-white fw-400 mb-0">
                  Une demande, jusqu&apos;à trois devis, un pro qui vient chez vous.
                </h3>
              </div>
            </div>
            <div className="col-md-7 col-xl-8" data-anime={slideX(30)}>
              <div className="border-radius-20px overflow-hidden position-relative bg-white box-shadow-extra-large p-7">
                <img
                  className="position-absolute bottom-0px right-0px w-40 xxl-w-30"
                  src={`${IMG}-02.jpg`}
                  alt=""
                  data-anime='{ "scale": [1.3, 1], "opacity": [0.5,1], "duration": 1200, "delay":0, "staggervalue": 300, "easing": "easeOutQuad" }'
                />
                <Pill className="text-dark-gray border border-color-extra-medium-gray mb-19">
                  Comment ça marche
                </Pill>
                <h3 className="alt-font fs-50 lg-fs-40 ls-minus-1px w-55 md-w-95 lg-w-85 xxl-w-75 mb-40px sm-mb-30px position-relative">
                  Décrivez le besoin, comparez les devis, choisissez votre pro.
                </h3>
                <SwitchLink
                  href="/services"
                  label="Voir les étapes"
                  icon="icon-feather-arrow-right"
                  className="btn-large btn-dark-gray btn-box-shadow btn-rounded"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* À propos */}
      <section className={`${SECTION_X} pt-0`}>
        <div className="container-fluid">
          <div className="row">
            <div className="col-lg-5 d-flex flex-column align-items-start md-mb-50px sm-mb-30px">
              <Pill className="text-white bg-base-color mb-auto md-mb-15px" anime={fadeUp()}>
                  À propos de Jeflink
                </Pill>
              <h2
                className="alt-font fw-500 ls-minus-2px mb-0"
                style={PERSPECTIVE}
                data-anime={lines()}
              >
                Des pros de confiance pour la maison, à Dakar.
              </h2>
            </div>
            <div className="col-lg-7 col-xl-6 offset-xl-1" data-anime={childsUp()}>
              <p>
                Jeflink met en relation particuliers et entreprises avec des artisans et techniciens
                dont l&apos;identité et le savoir-faire ont été contrôlés. Vous publiez votre
                besoin, les pros de votre quartier vous envoient un devis, vous choisissez. Le prix
                est fixé avant l&apos;intervention, et chaque mission se termine par un avis
                vérifié.
              </p>
              <div className="row row-cols-1 row-cols-sm-3 mt-22 lg-mt-18 md-mt-50px sm-mt-30px">
                <div className="col xs-mb-30px">
                  <h2 className="alt-font fw-500 mb-10px">{stats?.pros ?? "—"}</h2>
                  <span className="d-block w-60 xxl-w-100">
                    pros vérifiés dans {stats?.trades ?? 6} métiers.
                  </span>
                </div>
                <div className="col xs-mb-30px">
                  <h2 className="alt-font fw-500 mb-10px">{stats?.missions_done ?? "—"}</h2>
                  <span className="d-block w-60 xxl-w-100">missions terminées et notées.</span>
                </div>
                <div className="col">
                  <h2 className="alt-font fw-500 mb-10px">3</h2>
                  <span className="d-block w-60 xxl-w-100">
                    devis au plus, pour un choix clair.
                  </span>
                </div>
              </div>
              <div className="hover-arrow-swipe d-flex align-items-center justify-content-between border-top border-color-dark-gray pt-30px mt-30px">
                <span className="fs-20 sm-fs-18 lh-28 w-80 lg-w-85 sm-w-80">
                  Trouver un plombier à Ouakam doit être aussi simple que d&apos;envoyer un message.
                  C&apos;est pour ça que Jeflink existe.
                </span>
                <ArrowSwipe size={40} />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Les trois promesses, en cartes empilées */}
      <section className={`${SECTION_X} pt-0 pb-0`}>
        <div className="container-fluid">
          <div className="row">
            <div className="col-12">
              <div
                className="stack-card cards"
                data-scale="true"
                data-top-space="0"
                data-top-padding="0"
                data-top-space-first-item="30px"
              >
                {PROMISES.map((card, i) => (
                  <div
                    key={card.title}
                    className={`stack-item overflow-hidden${i ? " pt-30px" : ""}${i < PROMISES.length - 1 ? " md-mb-50px sm-mb-30px" : ""}`}
                    data-index={i}
                  >
                    <div
                      className="p-80px xs-p-25px md-p-40px xl-p-60px border-radius-20px h-800px sm-h-400px md-h-500px lg-h-600px xl-h-700px skrollr-parallax"
                      data-parallax-background-ratio="0.5"
                      style={{ backgroundImage: `url('${card.image}')` }}
                    >
                      <div
                        className="w-600px sm-w-100 lg-w-400px d-flex flex-column align-items-start h-100"
                        data-anime={childsUp()}
                      >
                        <div className="mb-auto d-flex align-items-center flex-wrap">
                          {card.tags.map((tag) => (
                            <a
                              key={tag}
                              className="fs-12 lh-14 fw-500 text-uppercase text-dark-gray bg-white border-radius-50px ps-20px pe-20px pt-10px pb-10px mb-10px me-10px d-inline-block"
                              href="/services"
                            >
                              {tag}
                            </a>
                          ))}
                        </div>
                        <a
                          href="/services"
                          className="fs-60 lg-fs-50 alt-font ls-minus-2px text-white mb-25px w-80 lg-w-100"
                        >
                          {card.title}
                        </a>
                        <p className="text-white mb-0 w-60 lg-w-100">{card.text}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Bandeau défilant des métiers */}
      <section className="big-section pt-6 md-pt-4 sm-pt-40px pb-0">
        <div className="container-fluid">
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

      {/* Les trois étapes, image collante */}
      <section className={`${SECTION_X} pt-0 pb-0 overflow-x-clip`}>
        <div className="container-fluid">
          <div className="text-center position-sticky top-40px w-290px lg-w-200px ms-auto d-none d-xl-block">
            <img
              className="animation-rotation-slow right-minus-100px lg-right-minus-50px position-relative"
              src={`${IMG}-06.png`}
              alt=""
            />
          </div>
          <div className="row mt-minus-300px lg-mt-0">
            <div className="col-md-6 sm-pb-40px" data-anime={fadeIn()}>
              <div className="position-sticky top-0 h-100vh lg-h-auto pt-12 pb-12 lg-pb-0 sm-pt-40px d-flex align-items-center">
                <img className="border-radius-20px" src={`${IMG}-07.jpg`} alt="" />
              </div>
            </div>
            <div className="col-md-6 col-xxl-5 ps-9 md-ps-15px xxl-ps-5 lg-pt-6 sm-pt-0 position-relative text-center text-md-start">
              {STEPS.map((step, i) => (
                <div
                  key={step.title}
                  className={`h-100vh lg-h-auto d-flex flex-column align-items-center align-items-md-start justify-content-center${i < STEPS.length - 1 ? " lg-mb-25 sm-mb-40px" : ""}${i === 0 ? " position-relative" : ""}`}
                >
                  <span className="fs-60 ls-minus-3px fw-300 opacity-2 d-block mb-6 position-relative">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div className="feature-box feature-box-left-icon-middle last-paragraph-no-margin mb-20px">
                    <div className="feature-box-icon me-10px">
                      <i className="bi bi-asterisk icon-extra-medium text-base-color" />
                    </div>
                    <div className="feature-box-content">
                      <span className="alt-font fs-22 sm-fs-20">{step.kicker}</span>
                    </div>
                  </div>
                  <h2 className="fw-500 alt-font ls-minus-2px">{step.title}</h2>
                  <p className="mb-30px w-75 xl-w-90 md-w-100 d-block">{step.text}</p>
                  <SwitchLink
                    href={step.cta.href}
                    label={step.cta.label}
                    icon={step.cta.icon}
                    className="btn-extra-large btn-dark-gray fw-400 btn-rounded btn-box-shadow"
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Appel à l'action */}
      <section
        className={`extra-big-section ${SECTION_X} cover-background`}
        style={{ backgroundImage: `url('${IMG}-lining-bg.jpg')` }}
      >
        <div className="container-fluid">
          <div className="row justify-content-center">
            <div className="col-xl-11 col-xxl-8 text-center">
              <Asterisk className="mb-25px" anime={fadeUp()}>Artisans et techniciens vérifiés</Asterisk>
              <h2
                className="alt-font fw-500 ls-minus-2px mb-45px sm-mb-30px"
                style={PERSPECTIVE}
                data-anime={lines()}
              >
                Jeflink, c&apos;est la façon simple et sûre de faire venir un pro chez soi.
              </h2>
              <div className="d-inline-flex flex-column flex-sm-row" data-anime={childsUp(600)}>
                <SwitchLink
                  href="/a-propos"
                  label="Découvrir Jeflink"
                  icon="icon-feather-zap"
                  className="btn-extra-large btn-dark-gray btn-rounded btn-box-shadow me-20px xs-me-0 xs-mb-15px"
                />
                <SwitchLink
                  href="/metiers"
                  label="Voir tous les métiers"
                  icon="icon-feather-layers"
                  className="btn-extra-large btn-transparent-dark-gray btn-rounded btn-box-shadow"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Engagements */}
      <section className={`${SECTION_X} pt-0 pb-0`}>
        <div className="container-fluid">
          <div className="bg-white border-radius-20px p-6 xs-p-25px lg-p-5 position-relative">
            <div
              className="bg-white-transparent-extra-light blur-box box-shadow-medium-bottom border-radius-100 border border-color-white position-absolute right-110px xl-right-50px md-right-20px top-minus-130px md-top-minus-100px d-none d-md-flex flex-column align-items-center justify-content-center lg-w-160px md-w-140px"
              data-anime={fadeIn(1200)}
            >
              <div className="w-130px h-130px lg-w-100px lg-h-100px md-w-90px md-h-90px box-shadow-medium-bottom position-absolute bg-white-transparent-extra-light blur-box border-radius-100 border border-color-white d-flex align-items-center justify-content-center">
                <img src={`${IMG}-09.png`} alt="" />
              </div>
              <img src={`${IMG}-08.png`} className="animation-rotation" alt="" />
            </div>
            <div className="row justify-content-between">
              <div
                className="col-lg-5 d-flex flex-column align-items-start md-mb-50px sm-mb-40px"
                data-anime={childsUp()}
              >
                <h3 className="alt-font ls-minus-2px fw-500">Nos engagements, noir sur blanc.</h3>
                <p className="w-75 lg-w-100 xl-w-90">
                  Ce qui vous protège à chaque demande, que vous soyez client ou pro. Ces règles
                  sont appliquées par la plateforme, pas seulement promises.
                </p>
                <Asterisk className="mt-auto">Pas de promesse en l&apos;air.</Asterisk>
              </div>
              <div className="col-lg-7 col-xxl-6" data-anime={childsUp()}>
                {PLEDGES.map(([n, a, b, tag], i) => (
                  <div
                    key={n}
                    className={`row border-top${i === PLEDGES.length - 1 ? " border-bottom" : ""} border-color-transparent-dark-light g-0`}
                  >
                    <div className="col-2 text-center align-self-center">
                      <span className="fs-20 lg-fs-18">{n}</span>
                    </div>
                    <div className="col-8 last-paragraph-no-margin p-30px lg-p-25px border-start border-color-transparent-dark-light">
                      <p className="fs-20 lg-fs-18">
                        {a} <span className="fw-600">{b}</span>
                      </p>
                    </div>
                    <div className="col-2 align-self-center text-center">
                      <span className="fs-20 lg-fs-18">{tag}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Nos pros */}
      <section className={`${SECTION_X} pt-30px`}>
        <div className="container-fluid">
          <div className="row row-cols-lg-3" data-anime={childsFade()}>
            <div className="col-lg md-mb-30px">
              <div
                className="bg-white border-radius-20px p-14 xs-p-25px md-p-5 xl-p-9 h-100 d-flex flex-column align-items-start"
                data-anime={childsUp()}
              >
                <Pill className="text-dark-gray border border-color-extra-medium-gray mb-auto md-mb-15px">
                  Nos pros
                </Pill>
                <h3 className="alt-font ls-minus-2px fw-500 mb-35px lg-mb-25px">
                  Des artisans de confiance, près de chez vous.
                </h3>
                <SwitchLink
                  href="/inscription?role=pro"
                  label="Devenir pro Jeflink"
                  icon="icon-feather-users"
                  className="btn-large btn-dark-gray btn-box-shadow btn-rounded"
                />
              </div>
            </div>
            {team.map((pro, i) => (
              <div key={pro.id} className={`col-md team-style-13${i === 0 ? " sm-mb-30px" : ""}`}>
                <figure className="mb-0 position-relative overflow-hidden border-radius-20px">
                  <img src={pro.photo} alt={`${pro.name}, ${pro.headline}`} />
                  <div className="team-overlay" />
                  <figcaption className="w-100 h-100 d-flex flex-wrap align-items-start">
                    <div className="social-icon d-flex flex-column flex-shrink-1 mb-auto p-40px lg-p-30px ms-auto">
                      <a
                        href={`/metiers/${pro.trades[0]?.slug ?? ""}`}
                        className="bg-white"
                        aria-label={`Voir le métier de ${pro.name}`}
                      >
                        <i className={`bi ${pro.trades[0]?.icon || "bi-tools"} fs-22`} />
                      </a>
                    </div>
                    <div className="w-100 mt-auto p-11 xl-p-9 sm-p-7">
                      <h4 className="team-member-name alt-font ls-minus-1px text-white d-block mb-5px">
                        {pro.name}
                      </h4>
                      <span className="member-designation fw-300 fs-18 lh-22 text-white d-block opacity-6">
                        {pro.headline}
                      </span>
                    </div>
                  </figcaption>
                </figure>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Questions fréquentes */}
      <section className={`${SECTION_X} pt-0`}>
        <div className="container-fluid">
          <div className="row">
            <div
              className="col-md-10 col-lg-5 d-flex flex-column align-items-start md-mb-25px sm-mb-15px"
              data-anime={childsUp()}
            >
              <Pill className="text-dark-gray border border-color-transparent-dark-light mb-auto">
                Questions fréquentes
              </Pill>
              <h3
                className="alt-font ls-minus-2px fw-500 mt-30px sm-mt-20px mb-0 w-90 lg-w-100"
                style={PERSPECTIVE}
                data-anime={lines()}
              >
                Ce qu&apos;il faut savoir avant votre première demande.
              </h3>
            </div>
            <div className="col-lg-7 col-xl-6 offset-xl-1">
              <div
                className="accordion accordion-style-02"
                id="faq"
                data-active-icon="icon-feather-chevron-up"
                data-inactive-icon="icon-feather-chevron-down"
                data-anime={childsUp()}
              >
                {FAQ.map((item, i) => {
                  const open = i === 0;
                  const last = i === FAQ.length - 1;
                  return (
                    <div
                      key={item.q}
                      className={`accordion-item${open ? " active-accordion" : ""}`}
                    >
                      <div
                        className={`accordion-header border-bottom${last ? " md-border-bottom-0" : ""} border-color-transparent-dark-light`}
                      >
                        <a
                          href="#"
                          data-bs-toggle="collapse"
                          data-bs-target={`#faq-${i}`}
                          aria-expanded={open}
                          data-bs-parent="#faq"
                        >
                          <div className="accordion-title text-dark-gray mb-0 position-relative pe-30px">
                            <i
                              className={`feather icon-feather-chevron-${open ? "up" : "down"} icon-extra-medium`}
                            />
                            <span className="fs-18 fw-500">{item.q}</span>
                          </div>
                        </a>
                      </div>
                      <div
                        id={`faq-${i}`}
                        className={`accordion-collapse collapse${open ? " show" : ""}`}
                        data-bs-parent="#faq"
                      >
                        <div
                          className={`accordion-body last-paragraph-no-margin border-bottom ${last ? "border-color-transparent" : "border-color-transparent-dark-light"}`}
                        >
                          <p>{item.a}</p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Logos (template, à remplacer par de vrais partenaires) */}
      <section className={`${SECTION_X} pt-0 pb-0`}>
        <div className="container-fluid">
          <div
            className="row row-cols-2 row-cols-lg-6 row-cols-sm-3 clients-style-05 m-0 text-center justify-content-center border-top border-color-dark-gray pt-4 pb-4 md-pt-50px md-pb-50px"
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
    </PageShell>
  );
}
