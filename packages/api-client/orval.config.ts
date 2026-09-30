import { defineConfig } from "orval";

// Généré depuis le contrat Django : make openapi (spectacular → schema.yaml → orval).
export default defineConfig({
  jeflink: {
    input: { target: "../../apps/api/schema.yaml" },
    output: {
      target: "src/generated/endpoints",
      schemas: "src/generated/model",
      mode: "tags-split",
      client: "react-query",
      httpClient: "fetch",
      clean: true,
      override: {
        mutator: { path: "src/http.ts", name: "jeflinkFetch" },
      },
    },
  },
});
