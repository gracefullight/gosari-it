import type { Config } from "orval";

const config: Config = {
  gosari: {
    input: {
      target: "../api/openapi.json",
    },
    output: {
      mode: "single",
      target: "src/lib/api/generated/endpoints.ts",
      schemas: "src/lib/api/generated/model",
      client: "react-query",
      clean: true,
      override: {
        mutator: {
          path: "src/lib/api/mutator.ts",
          name: "customFetch",
        },
      },
    },
  },
};

export default config;
