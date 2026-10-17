import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { SECTION_X, SwitchLink, opt } from "@/components/crafto";
import { PageShell } from "@/components/page-shell";
import { BadgesExplained, ProBadges } from "@/components/pro-badges";
import { getPros, getTrade, getTrades } from "@/lib/api";
import { formatRating, formatXOF } from "@/lib/format";

const IMG = "/crafto/images/demo-marketing-strategy";
const FALLBACK_PHOTOS = [
  opt(`${IMG}-01.jpg`),
  opt(`${IMG}-about-03.jpg`),
  "/images/services/pros.webp",
];

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const trade = await getTrade((await params).slug);
  return trade ? { title: trade.name, description: trade.tagline } : {};
}

export default async function TradePage({ params }: Props) {
  const { slug } = await params;
  const [trade, trades, pros] = await Promise.all([
    getTrade(slug),
    getTrades(),
    getPros(`?trade=${encodeURIComponent(slug)}`),
  ]);
  if (!trade) notFound();

  const index = trades.findIndex((t) => t.slug === trade.slug);
  const prev = trades[(index - 1 + trades.length) % trades.length];
  const next = trades[(index + 1) % trades.length];
  const askHref = `/espace/demandes/nouvelle?metier=${trade.slug}`;
  const shareUrl = encodeURIComponent(`http://localhost:3000/metiers/${trade.slug}`);
  const shareText = encodeURIComponent(`${trade.name} à Dakar avec Jeflink`);

  return (
    <PageShell>
      {/* Bannière */}
      <section className="big-section top-space-margin pb-0">
        <div className="container">
          <div className="row mb-40px sm-mb-25px">
            <div className="col-12 d-flex flex-wrap align-items-end justify-content-between gap-3">
              <h1 className="alt-font fw-500 ls-minus-2px mb-0">{trade.name}</h1>
              <SwitchLink
                href={askHref}
                label="Demander un devis"
                icon="icon-feather-edit"
                className="btn-large btn-base-color btn-rounded btn-box-shadow fw-400"
              />
            </div>
          </div>
          <div className="row">
            <div className="col-12 atropos" data-atropos>
              <div className="atropos-scale">
                <div className="atropos-rotate">
                  <div className="atropos-inner" data-atropos-offset="3">
                    <img
                      src={trade.image}
                      className="w-100 object-fit-cover border-radius-20px"
                      style={{ height: "380px" }}
                      alt=""
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Fiche */}
      <section className="pt-5">
        <div className="container">
          <div className="row row-cols-1 row-cols-md-4 row-cols-sm-2 justify-content-center align-items-center text-center">
            {[
              ["Métier", trade.name],
              ["À partir de", trade.starting_price ? formatXOF(trade.starting_price) : "Sur devis"],
              ["Pros vérifiés", String(trade.pros_count)],
              ["Zone", "Dakar et banlieue"],
            ].map(([label, value], i) => (
              <div
                key={label}
                className={`col${i < 3 ? " border-end border-color-transparent-dark-light" : ""}${i === 0 ? " sm-mb-30px xs-border-end-0" : i === 1 ? " sm-mb-30px sm-border-end-0" : i === 2 ? " xs-mb-30px xs-border-end-0" : ""}`}
              >
                <span className="d-block text-uppercase fs-14 alt-font lh-26 ls-05px">{label}</span>{" "}
                <span className="fs-17 fw-500">{value}</span>
              </div>
            ))}
          </div>
        </div>
      </section>
      <section
        className="one-fourth-screen"
        data-parallax-background-ratio="0.5"
        style={{ backgroundImage: `url('${opt(`${IMG}-hero-video-bg.jpg`)}')` }}
      />

      {/* Description */}
      <section className={`overflow-hidden ${SECTION_X} pb-0`}>
        <div className="container-fluid">
          <div className="row mb-50px sm-mb-30px">
            <div className="col-12">
              <img src={opt(`${IMG}-03.jpg`)} className="w-100 border-radius-20px" alt="" />
            </div>
          </div>
          <div className="row row-cols-1 row-cols-lg-2 mb-9">
            <div className="col md-mb-30px text-center text-lg-start">
              <h2 className="h5 alt-font mb-0 fw-500 w-80 lg-w-100">{trade.description}</h2>
            </div>
            <div className="col last-paragraph-no-margin text-center text-lg-start">
              <p>
                Prestations courantes : {trade.services.join(", ")}. Décrivez votre besoin, les pros
                vérifiés de votre quartier vous envoient jusqu&apos;à trois devis en F CFA.
              </p>
            </div>
          </div>
          <div className="row">
            <div className="col-12">
              <img src={opt(`${IMG}-04.jpg`)} className="w-100 border-radius-20px" alt="" />
            </div>
          </div>
        </div>
      </section>

      {/* Galerie */}
      <section className="overflow-hidden pb-0">
        <div className="container-fluid">
          <div className="row">
            <div className="col-12 col-md-12">
              <div className="outside-box-right-20 outside-box-left-20 sm-outside-box-right-0 sm-outside-box-left-0">
                <div
                  className="swiper magic-cursor drag-cursor"
                  data-slider-options='{ "slidesPerView": 1, "spaceBetween": 30, "loop": true, "autoplay": { "delay": 2000, "disableOnInteraction": false }, "keyboard": { "enabled": true, "onlyInViewport": true }, "breakpoints": { "992": { "slidesPerView": 3 }, "768": { "slidesPerView": 3 }, "320": { "slidesPerView": 1 } }, "effect": "slide" }'
                >
                  <div className="swiper-wrapper">
                    {["01", "02", "03", "04", "05", "06"].map((n) => (
                      <div key={n} className="swiper-slide">
                        <img
                          src={opt(`${IMG}-portfolio-${n}.jpg`)}
                          className="border-radius-20px"
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

      {/* Les pros de ce métier */}
      <section className={SECTION_X}>
        <div className="container-fluid">
          <div className="row mb-40px">
            <div className="col-12 text-center">
              <h2 className="h3 alt-font fw-500 ls-minus-2px mb-0">
                Les pros {trade.name.toLowerCase()}
              </h2>
            </div>
          </div>
          {pros.length === 0 ? (
            <p className="text-center fs-18">
              Aucun pro vérifié pour l&apos;instant dans ce métier. Publiez quand même votre demande
              : nous la transmettons dès qu&apos;un pro est disponible.
            </p>
          ) : (
            <>
              <div className="row row-cols-1 row-cols-md-3 justify-content-center">
                {pros.slice(0, 3).map((pro, i) => (
                  <div key={pro.id} className={`col team-style-13${i < 2 ? " sm-mb-30px" : ""}`}>
                    <figure className="mb-0 position-relative overflow-hidden border-radius-20px">
                      <img
                        src={pro.photo || FALLBACK_PHOTOS[i % FALLBACK_PHOTOS.length]}
                        className="w-100 object-fit-cover"
                        style={{ aspectRatio: "567 / 700" }}
                        alt={`${pro.name}, ${pro.headline}`}
                      />
                      <div className="team-overlay" />
                      <figcaption className="w-100 h-100 d-flex flex-wrap align-items-start">
                        <div className="w-100 mt-auto p-11 xl-p-9 sm-p-7">
                          <h3 className="h4 team-member-name alt-font ls-minus-1px text-white d-block mb-5px">
                            {pro.name}
                          </h3>
                          <span className="member-designation fw-300 fs-18 lh-22 text-white d-block opacity-6">
                            {pro.headline} · {pro.years_experience} ans d&apos;expérience
                            {pro.rating.count > 0 &&
                              ` · ★ ${formatRating(pro.rating.average)} (${pro.rating.count} avis)`}
                          </span>
                          <span className="d-block mt-10px">
                            <ProBadges verified confirmed={pro.is_confirmed} onDark />
                          </span>
                        </div>
                      </figcaption>
                    </figure>
                  </div>
                ))}
              </div>
              <div className="d-flex justify-content-center mt-30px">
                <BadgesExplained />
              </div>
            </>
          )}
        </div>
      </section>

      {/* Partager */}
      <section className="half-section pt-0">
        <div className="container">
          <div className="row row-cols-1 align-items-center justify-content-center">
            <div className="col text-center alt-font ls-1px mb-10px text-uppercase">
              Partager ce métier
            </div>
            <div className="col text-center elements-social social-icon-style-04">
              <ul className="large-icon dark mb-0">
                {[
                  ["whatsapp", "fa-whatsapp", `https://wa.me/?text=${shareText}%20${shareUrl}`],
                  [
                    "facebook",
                    "fa-facebook-f",
                    `https://www.facebook.com/sharer/sharer.php?u=${shareUrl}`,
                  ],
                  [
                    "twitter",
                    "fa-x-twitter",
                    `https://x.com/intent/post?url=${shareUrl}&text=${shareText}`,
                  ],
                  [
                    "linkedin",
                    "fa-linkedin-in",
                    `https://www.linkedin.com/sharing/share-offsite/?url=${shareUrl}`,
                  ],
                ].map(([cls, icon, href]) => (
                  <li key={cls}>
                    <a
                      className={cls}
                      href={href}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`Partager sur ${cls}`}
                    >
                      <i className={`fa-brands ${icon}`} />
                      <span />
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Métier précédent / suivant */}
      {prev && next && (
        <section className="half-section py-0">
          <div className="container-fluid">
            <div className="row row-cols-1 row-cols-xl-2 row-cols-lg-2 row-cols-md-2 border-radius-20px overflow-hidden">
              <div className="col portfolio-pagination px-0 bg-very-light-gray sm-border-bottom border-color-extra-medium-gray">
                <a
                  href={`/metiers/${prev.slug}`}
                  className="d-flex justify-content-between align-items-center ps-8 pe-8 pt-4 pb-4 lg-p-50px sm-p-35px"
                >
                  <div
                    className="bg-fancy-image cover-background"
                    style={{ backgroundImage: `url(${prev.image})` }}
                  />
                  <div className="alt-font fw-500 btn-slide-icon-left text-uppercase">
                    <span className="separator h-2px w-30px bg-dark-gray d-inline-block me-15px align-middle" />
                    <span className="d-none d-lg-inline-block fs-14">Métier précédent</span>
                  </div>{" "}
                  <span className="alt-font fs-28 d-block fw-500 ls-minus-1px">{prev.name}</span>
                </a>
              </div>
              <div className="col portfolio-pagination px-0 bg-very-light-gray">
                <a
                  href={`/metiers/${next.slug}`}
                  className="d-flex justify-content-between align-items-center ps-8 pe-8 pt-4 pb-4 lg-p-50px sm-p-35px"
                >
                  <div
                    className="bg-fancy-image cover-background"
                    style={{ backgroundImage: `url(${next.image})` }}
                  />{" "}
                  <span className="alt-font fs-28 d-block fw-500 ls-minus-1px">{next.name}</span>{" "}
                  <div className="alt-font fw-500 btn-slide-icon-right text-uppercase">
                    <span className="d-none d-lg-inline-block fs-14">Métier suivant</span>
                    <span className="separator h-2px w-30px bg-dark-gray d-inline-block ms-15px align-middle" />
                  </div>
                </a>
              </div>
            </div>
          </div>
        </section>
      )}
    </PageShell>
  );
}
