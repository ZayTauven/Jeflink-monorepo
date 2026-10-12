/** Préférences d'affichage de la console, gardées dans le navigateur (confort, pas de données). */
export const THEME_KEY = "jeflink-console:theme";
export const COLLAPSED_KEY = "jeflink-console:collapsed";

/**
 * Script inline exécuté avant le premier rendu : applique thème et menu replié sans clignotement.
 * Clair par défaut (décision 2026-10-12) ; sombre seulement si l'utilisateur l'a choisi.
 */
export const THEME_SCRIPT = `(function(){var d=document.documentElement,t=null,c=null;
try{t=localStorage.getItem(${JSON.stringify(THEME_KEY)});c=localStorage.getItem(${JSON.stringify(COLLAPSED_KEY)});}catch(e){}
d.setAttribute("data-ax-theme",t==="dark"?"dark":"light");if(c==="1")d.setAttribute("data-ax-collapsed","");})();`;
