/* The production build, beside the dev server rather than on top of it.

   `next dev` and `next build` both write `.next`; building while the dev
   server runs overwrites its chunks and the page silently stops hydrating.
   This builds into `.next-demo` (next.config.mjs reads NEXT_DIST_DIR) and
   serves it on 3001, so the fast copy and the dev copy never meet.

     npm run demo:build   then   npm run demo:start                         */
import { spawn } from "node:child_process";

const cmd = process.argv[2];
if (cmd !== "build" && cmd !== "start") {
  console.error("usage: node scripts/demo.mjs build|start");
  process.exit(2);
}
const args = cmd === "start" ? ["next", "start", "-p", process.env.PORT || "3001"] : ["next", "build"];
const child = spawn("npx", args, {
  stdio: "inherit",
  shell: process.platform === "win32",
  env: { ...process.env, NEXT_DIST_DIR: ".next-demo" },
});
child.on("exit", (code) => process.exit(code ?? 1));
