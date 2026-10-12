/** Badge en couronne de laurier : le laurier du template, nos arguments en texte. */
export function LaurelBadge({
  value,
  icon,
  label,
}: {
  value: string;
  icon: string;
  label: [string, string];
}) {
  return (
    <div className="jf-laurel">
      <img src="/images/accueil/laurier.png" alt="" width={130} height={90} />
      <div className="jf-laurel-text">
        <span className="jf-laurel-value">{value}</span>
        <i className={`bi ${icon}`} aria-hidden="true" />
        <span className="jf-laurel-label">
          {label[0]}
          <br />
          {label[1]}
        </span>
      </div>
    </div>
  );
}
