"use client";

import Script from "next/script";
import { useState } from "react";

/**
 * Scripts du template Crafto (jQuery, plugins, main.js), chargés dans l'ordre et APRÈS
 * l'hydratation React : avant, leurs modifications du DOM seraient effacées par React.
 * main.js initialise une partie des effets sur `window.load`, déjà passé à ce stade : on le
 * rejoue une fois le script chargé.
 */
export function CraftoScripts() {
  const [step, setStep] = useState(0);
  return (
    <>
      <Script src="/crafto/js/jquery.js" strategy="afterInteractive" onLoad={() => setStep(1)} />
      {step >= 1 && <Script src="/crafto/js/vendors.min.js" onLoad={() => setStep(2)} />}
      {step >= 2 && <Script src="/crafto/js/main.js" onLoad={replayWindowLoad} />}
    </>
  );
}

function replayWindowLoad() {
  const jq = (window as unknown as { jQuery?: (el: Window) => { trigger: (e: string) => void } })
    .jQuery;
  if (!jq) return;
  if (document.readyState === "complete") jq(window).trigger("load");
}
