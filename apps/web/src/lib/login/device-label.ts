// Libellé de l'appareil web, affiché dans « Mon compte › Appareils » et dans l'écran « Autres
// appareils » d'un autre appareil (« Chrome · Android »). Navigateur et système seulement :
// rien qui identifie la personne.

const BROWSERS: Array<[RegExp, string]> = [
  [/SamsungBrowser\//, "Samsung Internet"],
  [/OPR\/|Opera/, "Opera"],
  [/Edg\//, "Edge"],
  [/Firefox\//, "Firefox"],
  [/Chrome\//, "Chrome"],
  [/Safari\//, "Safari"],
];
const SYSTEMS: Array<[RegExp, string]> = [
  [/Android/, "Android"],
  [/iPhone|iPad|iPod/, "iOS"],
  [/Windows/, "Windows"],
  [/Mac OS X|Macintosh/, "macOS"],
  [/Linux/, "Linux"],
];

export function webDeviceLabel(userAgent: string): string {
  const browser = BROWSERS.find(([pattern]) => pattern.test(userAgent))?.[1] ?? "Navigateur";
  const system = SYSTEMS.find(([pattern]) => pattern.test(userAgent))?.[1];
  return system ? `${browser} · ${system}` : browser;
}
