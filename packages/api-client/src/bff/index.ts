// BFF serveur des apps Next (web, console). `server-only` : importer ce module depuis du code
// client casse le build, pour qu'aucun secret ni jeton ne parte dans un bundle navigateur.
import "server-only";

export { COOKIES } from "./cookies.ts";
export { createBff } from "./handlers.ts";
export type { BffConfig, ServerCallOptions } from "./handlers.ts";
export { safeApiPath, safeNextPath } from "./paths.ts";
