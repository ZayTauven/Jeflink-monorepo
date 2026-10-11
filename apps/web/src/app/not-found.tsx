import { SECTION_X, SwitchLink } from "@/components/crafto";
import { PageShell } from "@/components/page-shell";

export default function NotFound() {
  return (
    <PageShell>
      <section className={`${SECTION_X} top-space-margin`}>
        <div className="container-fluid">
          <div className="bg-white border-radius-20px p-12 sm-p-7 text-center">
            <span className="alt-font fs-150 sm-fs-90 fw-500 ls-minus-5px text-base-color d-block">
              404
            </span>
            <h1 className="h3 alt-font fw-500 ls-minus-2px">Cette page n&apos;existe pas.</h1>
            <p className="mb-30px">
              Le lien est peut-être ancien, ou la page a changé d&apos;adresse.
            </p>
            <SwitchLink
              href="/"
              label="Retour à l'accueil"
              icon="icon-feather-home"
              className="btn-large btn-dark-gray btn-rounded btn-box-shadow"
            />
          </div>
        </div>
      </section>
    </PageShell>
  );
}
