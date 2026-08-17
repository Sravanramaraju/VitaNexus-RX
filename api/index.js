import { createApp } from "../server/app.js";

const clinicalApi = createApp();

// Vercel rewrites /api/:path* here. Restore the original path before handing
// the request to Express, whose routes are mounted under /api/v1.
export default function handler(req, res) {
  const url = new URL(req.url || "/api", "http://localhost");
  const path = url.searchParams.get("path") || "";
  url.searchParams.delete("path");
  req.url = `/api/${path}${url.search}`;
  return clinicalApi(req, res);
}
