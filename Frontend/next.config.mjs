/** @type {import('next').NextConfig} */
const nextConfig = { output: process.env.NEXT_LOCAL_PREVIEW === "1" ? undefined : "standalone", distDir: process.env.NEXT_DIST_DIR || ".next" };
export default nextConfig;
