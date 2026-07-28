import type { NextConfig } from "next";

const nextConfig: NextConfig = {

  basePath: "/app",
  assetPrefix: "/app",
  trailingSlash: true,
  output: "export",
  images: {
    // Static export can't run Next's Image Optimization server.
    unoptimized: true,
  },
};

export default nextConfig;
