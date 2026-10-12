import { defineCloudflareConfig } from "@opennextjs/cloudflare";

const config = defineCloudflareConfig({});

// `npm run build` runs `opennextjs-cloudflare build`, so OpenNext must call
// `next build` directly here to avoid invoking `npm run build` recursively.
config.buildCommand = "npx next build";

export default config;
