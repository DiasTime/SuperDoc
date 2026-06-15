/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@docres/shared-types"],
  // "standalone" output uses symlinks, which Windows blocks without admin /
  // Developer Mode. Only enable it for the Docker image build (NEXT_STANDALONE=1).
  ...(process.env.NEXT_STANDALONE === "1" ? { output: "standalone" } : {}),
};

export default nextConfig;
