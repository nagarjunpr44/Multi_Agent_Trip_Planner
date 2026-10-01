import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";
const API = process.env.API_URL ?? "http://127.0.0.1:8000";

// Production: a static export that FastAPI serves from web/out.
// Development: `next dev` proxies API calls to FastAPI (static export forbids rewrites).
const nextConfig: NextConfig = isDev
  ? {
      async rewrites() {
        return [
          { source: "/trips", destination: `${API}/trips` },
          { source: "/trips/:path*", destination: `${API}/trips/:path*` },
        ];
      },
    }
  : { output: "export", trailingSlash: true, images: { unoptimized: true } };

export default nextConfig;
