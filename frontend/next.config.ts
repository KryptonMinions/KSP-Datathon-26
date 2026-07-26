import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export for Catalyst Web Client Hosting — this app has no SSR
  // routes or middleware, it's a pure client hitting NEXT_PUBLIC_API_URL.
  output: "export",
  images: {
    // Static export can't run Next's Image Optimization server.
    unoptimized: true,
  },
};

export default nextConfig;
