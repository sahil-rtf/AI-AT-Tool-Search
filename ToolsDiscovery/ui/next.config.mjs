/** @type {import('next').NextConfig} */
const nextConfig = {
  // Proxy /api/* → Flask backend at localhost:5000
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:5000/:path*",
      },
    ];
  },
};

export default nextConfig;
