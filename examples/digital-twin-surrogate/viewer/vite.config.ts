import { createReadStream, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, type Plugin } from "vite";

const viewerRoot = dirname(fileURLToPath(import.meta.url));
const demoScene = resolve(viewerRoot, "../scene/assets/surrogate-cell.glb");

function demoScenePlugin(): Plugin {
  const install = (middlewares: {
    use: (
      route: string,
      handler: (
        request: { method?: string },
        response: {
          end: () => void;
          setHeader: (name: string, value: string | number) => void;
          statusCode: number;
        },
      ) => void,
    ) => void;
  }) => {
    middlewares.use("/__opensdl_demo__/scene.glb", (request, response) => {
      try {
        const size = statSync(demoScene).size;
        response.setHeader("Content-Type", "model/gltf-binary");
        response.setHeader("Content-Length", size);
        response.setHeader("Cache-Control", "no-store");
        if (request.method === "HEAD") {
          response.end();
          return;
        }
        createReadStream(demoScene).pipe(response as never);
      } catch {
        response.statusCode = 404;
        response.end();
      }
    });
  };

  return {
    name: "opensdl-demo-scene",
    configureServer(server) {
      install(server.middlewares);
    },
    configurePreviewServer(server) {
      install(server.middlewares);
    },
  };
}

export default defineConfig({
  base: "/viewer/",
  build: {
    chunkSizeWarningLimit: 700,
    emptyOutDir: true,
    outDir: "static",
    sourcemap: false,
  },
  plugins: [demoScenePlugin()],
  server: {
    host: "127.0.0.1",
    port: 4173,
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
  },
});
