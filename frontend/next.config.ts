import type { NextConfig } from "next";

import { ApiError, resolveApiBaseUrl } from "./lib/answer-api.mjs";

const isVercel = process.env.VERCEL === "1";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

if (isVercel && !apiBaseUrl) {
  throw new Error(
    "Set NEXT_PUBLIC_API_BASE_URL to Railway's public HTTPS API URL for frontend-only Vercel deployments.",
  );
}

if (isVercel && apiBaseUrl) {
  try {
    const resolvedApiBaseUrl = resolveApiBaseUrl(apiBaseUrl, false);
    if (!resolvedApiBaseUrl.startsWith("https://")) {
      throw new Error(
        "NEXT_PUBLIC_API_BASE_URL must be Railway's public HTTPS API URL for frontend-only Vercel deployments.",
      );
    }
  } catch (error) {
    if (error instanceof ApiError) {
      throw new Error(
        "NEXT_PUBLIC_API_BASE_URL must be a non-local HTTPS URL without credentials, query, or fragment.",
      );
    }
    throw error;
  }
}

const nextConfig: NextConfig = {
  ...(isVercel && apiBaseUrl ? { env: { NEXT_PUBLIC_API_BASE_URL: apiBaseUrl } } : {}),
  output: "standalone",
  outputFileTracingRoot: __dirname,
};

export default nextConfig;
