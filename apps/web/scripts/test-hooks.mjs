// Tests node:test : le paquet `next` n'a pas de carte `exports`, et Node ESM exige alors
// l'extension (`next/server.js`). Ce crochet l'ajoute aux imports `next/…`, comme le fait le
// bundler de Next, pour que le code testé garde ses imports habituels.
import { register } from "node:module";

register("./next-resolve-hook.mjs", import.meta.url);
