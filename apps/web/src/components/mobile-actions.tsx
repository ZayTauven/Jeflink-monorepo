/**
 * Barre d'actions fixée en bas de l'écran sur mobile : « Faire une demande » et WhatsApp.
 * Le numéro WhatsApp vient de SUPPORT_WHATSAPP_NUMBER (serveur) ; sans lui, seul le premier
 * bouton s'affiche.
 */
export function MobileActions() {
  const digits = (process.env.SUPPORT_WHATSAPP_NUMBER ?? "").replace(/\D/g, "");
  const whatsapp = digits
    ? `https://wa.me/${digits}?text=${encodeURIComponent("Bonjour Jeflink, j'ai besoin d'un pro.")}`
    : null;
  return (
    <nav className="jf-mobile-actions d-md-none" aria-label="Actions rapides">
      <a
        href="/espace/demandes/nouvelle"
        className="btn btn-medium btn-base-color btn-rounded btn-box-shadow flex-grow-1"
      >
        <i className="feather icon-feather-edit me-10px" aria-hidden="true" />
        Faire une demande
      </a>
      {whatsapp && (
        <a
          href={whatsapp}
          target="_blank"
          rel="noreferrer"
          className="btn btn-medium btn-dark-gray btn-rounded btn-box-shadow"
        >
          <i className="fa-brands fa-whatsapp me-10px" aria-hidden="true" />
          WhatsApp
        </a>
      )}
    </nav>
  );
}
