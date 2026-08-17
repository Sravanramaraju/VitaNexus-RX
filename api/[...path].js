import { createApp } from "../server/app.js";

// Vercel routes every /api/* request to this serverless Express handler.
// The application keeps its existing /api/v1 routes unchanged.
export default createApp();
