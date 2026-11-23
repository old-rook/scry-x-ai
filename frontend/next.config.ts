import type { NextConfig } from "next";

import { ApiError, resolveApiBaseUrl } from "./lib/answer-api.mjs";

if (process.env.VERCEL === "1") {
  if (!process.env.NEXT_PUBLIC_API_BASE_URL) {
    throw new Error("Set NEXT_PUBLIC_API_BASE_URL to the HTTPS backend API base before deploying.");
  }
  try {
    resolveApiBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL, false);
  } catch (error) {
    if (error instanceof ApiError) {
      throw new Error("NEXT_PUBLIC_API_BASE_URL must be a non-local HTTPS API URL without credentials, query, or fragment.");
    }
    throw error;
  }
}

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: __dirname,
};

export default nextConfig;
