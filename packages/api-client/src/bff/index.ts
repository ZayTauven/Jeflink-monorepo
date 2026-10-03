// BFF serveur des apps Next (web, console). `server-only` : importer ce module depuis du code
// client casse le build, pour qu'aucun secret ni jeton ne parte dans un bundle navigateur.
// Le code client importe les chemins par `@jeflink/api-client/paths`.
import "server-only";

export { COOKIES } from "./cookies.ts";
export { createBff } from "./handlers.ts";
export type { BffConfig, BffSecurityEvent, BffServer } from "./handlers.ts";
export { REFRESH_LOCK, safeApiPath, safeNextPath } from "./paths.ts";
