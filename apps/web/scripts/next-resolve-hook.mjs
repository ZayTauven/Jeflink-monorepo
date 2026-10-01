// Crochet de résolution des tests : `next/server` → `next/server.js` (voir test-hooks.mjs).
export async function resolve(specifier, context, nextResolve) {
  if (/^next\/[^.]+$/.test(specifier)) return nextResolve(`${specifier}.js`, context);
  return nextResolve(specifier, context);
}
