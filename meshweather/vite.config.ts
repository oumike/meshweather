import { execSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

function resolveAppVersion(): string {
  // Keep frontend version in sync with releases by preferring VERSION, then tags.
  const appDir = fileURLToPath(new URL(".", import.meta.url));
  const workspaceRoot = resolve(appDir, "..");
  const versionFile = resolve(workspaceRoot, "VERSION");

  if (existsSync(versionFile)) {
    const fromFile = readFileSync(versionFile, "utf8").trim();
    if (fromFile) {
      return fromFile;
    }
  }

  try {
    const fromTag = execSync("git describe --tags --abbrev=0", {
      cwd: workspaceRoot,
      stdio: ["ignore", "pipe", "ignore"],
    })
      .toString()
      .trim();
    if (fromTag) {
      return fromTag;
    }
  } catch {
    // Ignore missing git metadata and fall through to package version.
  }

  return process.env.npm_package_version ?? "unknown";
}

const appVersion = resolveAppVersion();

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
  },
  server: {
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_API_TARGET || "http://127.0.0.1:8080",
        changeOrigin: true,
      },
      "/health": {
        target: process.env.VITE_DEV_API_TARGET || "http://127.0.0.1:8080",
        changeOrigin: true,
      },
    },
  },
});
