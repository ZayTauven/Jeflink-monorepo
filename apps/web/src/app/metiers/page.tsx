import type { Metadata } from "next";

import { fadeIn, fadeUp, lines, PERSPECTIVE, Pill, SECTION_X, slideX } from "@/components/crafto";
import { PageShell } from "@/components/page-shell";
import { getTrades } from "@/lib/api";
import { formatXOF } from "@/lib/format";

export const metadata: Metadata = { title: "Métiers" };

export default async function TradesPage() {
  const trades = await getTrades();

  return (
    <PageShell>
      {/* Titre de page */}
      <section className={`${SECTION_X} pt-0 md-pt-50px pb-0 top-space-margin`}>
        <div className="container-fluid">
          <div className="row">
            <div className="col-md-5 col-xl-4 sm-mb-30px">
              <div className="bg-white border-radius-20px p-14 sm-p-7 xl-p-12 h-100 d-flex flex-column align-items-start">
                <Pill className="text-white bg-base-color mb-auto" anime={fadeUp()}>
                  Nos métiers
                </Pill>{" "}
                <h1
                  className="h3 alt-font fw-500 ls-minus-2px mb-0 mt-30 md-mt-0 pt-70px"
                  style={PERSPECTIVE}
                  data-anime={lines()}
                >
                  Six métiers, des pros vérifiés dans chacun.
                </h1>
              </div>
            </div>
            <div className="col-md-7 col-xl-8" data-anime={fadeIn()}>
              <img
                className="border-radius-20px object-fit-cover h-100"
                src="/crafto/images/demo-marketing-strategy-contact-02.jpg"
                alt=""
              />
            </div>
          </div>
        </div>
      </section>

      {/* Grille des métiers */}
      <section className={`${SECTION_X} pt-15px`}>
        <div className="container-fluid">
          <div className="row sm-m-0">
            <div className="col-12 p-0">
              {trades.length === 0 ? (
                <p className="text-center fs-20 pt-50px">
                  Les métiers n&apos;ont pas pu être chargés. L&apos;API est-elle lancée ?
                </p>
              ) : (
                <ul className="portfolio-elegant portfolio-wrapper grid-loading grid grid-2col xxl-grid-2col xl-grid-2col lg-grid-2col md-grid-1col sm-grid-1col xs-grid-1col gutter-extra-large">
                  <li className="grid-sizer" />
                  {trades.map((trade, i) => (
                    <li key={trade.slug} className="grid-item transition-inner-all">
                      <div
                        className="portfolio-box border-radius-20px"
                        data-anime={slideX(i % 2 ? 50 : -50, 0)}
                      >
                        <div className="portfolio-image">
                          <img src={trade.image} alt="" />
                        </div>
                        <div className="portfolio-content w-100 p-10 md-p-7 d-flex flex-column align-items-start text-start">
                          <div className="d-flex align-items-center flex-wrap mb-auto">
                            {trade.services.slice(0, 3).map((service) => (
                              <a
                                key={service}
                                href={`/metiers/${trade.slug}`}
                                className="fs-12 lh-14 fw-500 text-uppercase text-dark-gray bg-white border-radius-50px ps-20px pe-20px pt-10px pb-10px me-10px mb-10px sm-me-5px sm-mb-5px d-inline-block"
                              >
                                {service}
                              </a>
                            ))}
                          </div>{" "}
                          <a
                            href={`/metiers/${trade.slug}`}
                            className="fs-60 lg-fs-45 xl-fs-50 alt-font ls-minus-2px w-75 sm-w-100 md-w-55 xxl-w-100 text-white mb-25px sm-mb-15px"
                          >
                            {trade.name}
                          </a>{" "}
                          <p className="text-white mb-0 w-65 md-w-75 sm-w-100 xxl-w-100">
                            {trade.tagline}
                            {trade.starting_price
                              ? ` À partir de ${formatXOF(trade.starting_price)}.`
                              : ""}
                          </p>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </section>
    </PageShell>
  );
}
