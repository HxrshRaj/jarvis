import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
/** @type {import('next').NextConfig} */
export default { reactStrictMode: true, outputFileTracingRoot: root };
