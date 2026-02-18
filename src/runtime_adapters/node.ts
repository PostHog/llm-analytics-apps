import path from "path";
import fs from "fs/promises";
import { execFile } from "child_process";
import { promisify } from "util";
import { Socket } from "net";
import { createHash } from "crypto";
import SubprocessAdapter from "./utils/subprocess.js";
import type { Message, Provider, RuntimeTool } from "../types.js";

const execFileAsync = promisify(execFile);
const NODE_RUNTIME_DIR = path.join(process.cwd(), "runtimes", "node");
const NODE_DEPS_CONFIG_PATH = path.join(NODE_RUNTIME_DIR, ".deps-config.json");
const NODE_LOCAL_BUILD_CACHE_PATH = path.join(
  NODE_RUNTIME_DIR,
  ".local-build-cache.json",
);
const ROOT_DIR = process.cwd();
const LOG_DIR = path.join(ROOT_DIR, ".logs");
const NODE_SETUP_LOG_PATH = path.join(LOG_DIR, "runtime-node-setup.log");

type NodeDepsConfig =
  | { mode: "default" }
  | { mode: "local"; jsPath: string }
  | { mode: "version"; aiVersion?: string; nodeVersion?: string };

type NodeLocalBuildCache = {
  aiHash?: string;
  nodeHash?: string;
};

export default class NodeAdapter extends SubprocessAdapter {
  override id(): string {
    return "node";
  }

  override name(): string {
    return "Node";
  }

  getSocketPath(): string {
    return path.join(NODE_RUNTIME_DIR, "adapter.sock");
  }

  getCommand(): { command: string; args: string[] } {
    const adapterPath = path.join(NODE_RUNTIME_DIR, "dist", "adapter.js");
    return { command: "node", args: [adapterPath] };
  }

  async ensureRuntimeSetup(): Promise<void> {
    await this.ensurePostHogDependencies();

    const requiredProvider = path.join(
      NODE_RUNTIME_DIR,
      "dist",
      "providers",
      "base.js",
    );
    const providerExists = await fs
      .access(requiredProvider)
      .then(() => true)
      .catch(() => false);

    if (!providerExists) {
      throw new Error(
        `Missing Node runtime providers at ${requiredProvider}. Re-run setup to restore runtime provider artifacts.`,
      );
    }
  }

  private getDesiredDepsConfig(): NodeDepsConfig {
    const jsPath = process.env["POSTHOG_JS_PATH"]?.trim();
    if (jsPath) {
      return { mode: "local", jsPath };
    }

    const aiVersion = process.env["POSTHOG_JS_AI_VERSION"]?.trim();
    const nodeVersion = process.env["POSTHOG_JS_NODE_VERSION"]?.trim();
    if (aiVersion || nodeVersion) {
      const config: NodeDepsConfig = { mode: "version" };
      if (aiVersion) {
        config.aiVersion = aiVersion;
      }
      if (nodeVersion) {
        config.nodeVersion = nodeVersion;
      }
      return config;
    }

    return { mode: "default" };
  }

  private async readAppliedDepsConfig(): Promise<NodeDepsConfig | null> {
    try {
      const raw = await fs.readFile(NODE_DEPS_CONFIG_PATH, "utf8");
      return JSON.parse(raw) as NodeDepsConfig;
    } catch {
      return null;
    }
  }

  private async writeAppliedDepsConfig(config: NodeDepsConfig): Promise<void> {
    await fs.mkdir(NODE_RUNTIME_DIR, { recursive: true });
    await fs.writeFile(
      NODE_DEPS_CONFIG_PATH,
      JSON.stringify(config, null, 2),
      "utf8",
    );
  }

  private async ensureNodeModules(): Promise<void> {
    const nodeModulesPath = path.join(ROOT_DIR, "node_modules");
    const exists = await fs
      .access(nodeModulesPath)
      .then(() => true)
      .catch(() => false);

    if (!exists) {
      await this.logSetup("Installing Node dependencies...");
      await execFileAsync("pnpm", ["--dir", ROOT_DIR, "install"]);
    }
  }

  private async ensurePostHogDependencies(): Promise<void> {
    await this.ensureNodeModules();

    const desired = this.getDesiredDepsConfig();
    const applied = await this.readAppliedDepsConfig();
    const modeUnchanged = JSON.stringify(desired) === JSON.stringify(applied);

    if (modeUnchanged && desired.mode !== "local") {
      return;
    }

    if (desired.mode === "local") {
      const absoluteJsPath = path.resolve(ROOT_DIR, desired.jsPath);
      const aiPackagePath = path.join(absoluteJsPath, "packages", "ai");
      const nodePackagePath = path.join(absoluteJsPath, "packages", "node");
      const nodeModulesRoot = path.join(ROOT_DIR, "node_modules");
      const aiTargetPath = path.join(nodeModulesRoot, "@posthog", "ai");
      const nodeTargetPath = path.join(nodeModulesRoot, "posthog-node");

      const localPackagesExist = await Promise.all([
        fs
          .access(path.join(aiPackagePath, "package.json"))
          .then(() => true)
          .catch(() => false),
        fs
          .access(path.join(nodePackagePath, "package.json"))
          .then(() => true)
          .catch(() => false),
      ]).then(([aiExists, nodeExists]) => aiExists && nodeExists);

      if (!localPackagesExist) {
        throw new Error(
          `POSTHOG_JS_PATH is set but invalid: ${absoluteJsPath}. Expected to find packages/ai/package.json and packages/node/package.json.`,
        );
      }

      console.log(
        `Using local PostHog JS packages from ${absoluteJsPath} for Node runtime...`,
      );
      await this.logSetup(
        `Using local PostHog JS packages from ${absoluteJsPath}.`,
      );

      await this.ensureLocalPostHogPackagesBuilt({
        aiPackagePath,
        nodePackagePath,
      });

      // Match legacy run.sh behavior:
      // install deps normally, then replace the two packages with local symlinks
      // without modifying package.json.
      await fs.rm(aiTargetPath, { recursive: true, force: true });
      await fs.rm(nodeTargetPath, { recursive: true, force: true });
      await fs.mkdir(path.join(nodeModulesRoot, "@posthog"), {
        recursive: true,
      });
      await fs.symlink(aiPackagePath, aiTargetPath, "dir");
      await fs.symlink(nodePackagePath, nodeTargetPath, "dir");

      if (!modeUnchanged) {
        await this.writeAppliedDepsConfig(desired);
      }
      return;
    }

    if (desired.mode === "version") {
      const addArgs = ["--dir", ROOT_DIR, "add"];

      if (desired.aiVersion) {
        addArgs.push(`@posthog/ai@${desired.aiVersion}`);
      } else {
        addArgs.push("@posthog/ai");
      }

      if (desired.nodeVersion) {
        addArgs.push(`posthog-node@${desired.nodeVersion}`);
      } else {
        addArgs.push("posthog-node");
      }

      await this.logSetup("Installing version-locked PostHog JS packages...");
      await execFileAsync("pnpm", addArgs);
      await this.writeAppliedDepsConfig(desired);
      return;
    }

    if (applied && applied.mode !== "default") {
      await this.logSetup("Restoring PostHog JS dependencies from package.json.");
      await execFileAsync("pnpm", ["--dir", ROOT_DIR, "install"]);
    }

    await this.writeAppliedDepsConfig(desired);
  }

  private async readLocalBuildCache(): Promise<NodeLocalBuildCache> {
    try {
      const raw = await fs.readFile(NODE_LOCAL_BUILD_CACHE_PATH, "utf8");
      return JSON.parse(raw) as NodeLocalBuildCache;
    } catch {
      return {};
    }
  }

  private async writeLocalBuildCache(cache: NodeLocalBuildCache): Promise<void> {
    await fs.mkdir(NODE_RUNTIME_DIR, { recursive: true });
    await fs.writeFile(
      NODE_LOCAL_BUILD_CACHE_PATH,
      JSON.stringify(cache, null, 2),
      "utf8",
    );
  }

  private async ensureLocalPostHogPackagesBuilt(paths: {
    aiPackagePath: string;
    nodePackagePath: string;
  }): Promise<void> {
    const cache = await this.readLocalBuildCache();
    const aiHash = await this.hashDirectory(paths.aiPackagePath);
    const nodeHash = await this.hashDirectory(paths.nodePackagePath);

    if (cache.aiHash !== aiHash) {
      await this.logSetup("Rebuilding local @posthog/ai package.");
      await execFileAsync("pnpm", ["--dir", paths.aiPackagePath, "run", "build"]);
    } else {
      await this.logSetup("Local @posthog/ai unchanged, skipping rebuild.");
    }

    if (cache.nodeHash !== nodeHash) {
      await this.logSetup("Rebuilding local posthog-node package.");
      await execFileAsync("pnpm", [
        "--dir",
        paths.nodePackagePath,
        "run",
        "build",
      ]);
    } else {
      await this.logSetup("Local posthog-node unchanged, skipping rebuild.");
    }

    if (cache.aiHash !== aiHash || cache.nodeHash !== nodeHash) {
      await this.writeLocalBuildCache({ aiHash, nodeHash });
    }
  }

  private async logSetup(message: string): Promise<void> {
    const line = `[${new Date().toISOString()}] ${message}\n`;
    await fs.mkdir(LOG_DIR, { recursive: true });
    await fs.appendFile(NODE_SETUP_LOG_PATH, line, "utf8");
  }

  private async hashDirectory(directory: string): Promise<string> {
    const hash = createHash("sha256");
    const files = await this.collectHashableFiles(directory, directory);

    for (const relativePath of files) {
      const fullPath = path.join(directory, relativePath);
      const content = await fs.readFile(fullPath);
      hash.update(relativePath);
      hash.update(content);
    }

    return hash.digest("hex");
  }

  private async collectHashableFiles(
    rootDir: string,
    currentDir: string,
  ): Promise<string[]> {
    const entries = await fs.readdir(currentDir, { withFileTypes: true });
    const files: string[] = [];

    for (const entry of entries) {
      const fullPath = path.join(currentDir, entry.name);
      const relativePath = path.relative(rootDir, fullPath);

      if (entry.isDirectory()) {
        if (
          entry.name === "node_modules" ||
          entry.name === "dist" ||
          entry.name === ".git" ||
          entry.name === ".turbo" ||
          entry.name === ".next" ||
          entry.name === "coverage"
        ) {
          continue;
        }

        const nested = await this.collectHashableFiles(rootDir, fullPath);
        files.push(...nested);
        continue;
      }

      if (
        relativePath.endsWith(".map") ||
        relativePath.endsWith(".log") ||
        relativePath.endsWith(".tmp") ||
        relativePath.endsWith(".swp")
      ) {
        continue;
      }

      files.push(relativePath);
    }

    files.sort((a, b) => a.localeCompare(b));
    return files;
  }

  override async getProviders(): Promise<Provider[]> {
    const response = await this.sendMessage<{ providers: Provider[] }>({
      action: "get_providers",
    });
    return response.providers;
  }

  override async setProviderOption(
    providerId: string,
    optionId: string,
    value: string | boolean,
  ): Promise<void> {
    await this.sendMessage<{ success: boolean }>({
      action: "set_provider_option",
      provider: providerId,
      option_id: optionId,
      value,
    });
  }

  override async chat(
    providerId: string,
    messages: Message[],
  ): Promise<Message> {
    const response = await this.sendMessage<{ message: Message }>({
      action: "chat",
      provider: providerId,
      messages,
    });
    return response.message;
  }

  override async runModeTest(
    providerId: string,
    mode: string,
  ): Promise<Message> {
    const response = await this.sendMessage<{ message: Message }>({
      action: "run_mode_test",
      provider: providerId,
      mode,
    });
    return response.message;
  }

  override async getTools(): Promise<RuntimeTool[]> {
    const response = await this.sendMessage<{ tools: RuntimeTool[] }>({
      action: "list_tools",
    });
    return response.tools;
  }

  override async runTool(toolId: string, providerId?: string): Promise<Message> {
    const response = await this.sendMessage<{ message: Message }>({
      action: "run_tool",
      tool_id: toolId,
      provider: providerId,
    });
    return response.message;
  }

  override async chatStream(
    providerId: string,
    messages: Message[],
    onChunk: (chunk: string) => void,
  ): Promise<Message> {
    const socketPath = this.getSocketPath();

    return new Promise((resolve, reject) => {
      const socket = new Socket();
      let buffer = "";
      let done = false;

      const cleanup = () => {
        socket.removeAllListeners();
        socket.destroy();
      };

      socket.on("data", (data: Buffer) => {
        buffer += data.toString();

        let newlineIndex = buffer.indexOf("\n");
        while (newlineIndex !== -1) {
          const line = buffer.slice(0, newlineIndex).trim();
          buffer = buffer.slice(newlineIndex + 1);

          if (line) {
            try {
              const message = JSON.parse(line);
              if (
                message.type === "chunk" &&
                typeof message.chunk === "string"
              ) {
                onChunk(message.chunk);
              } else if (message.type === "done" && message.message) {
                done = true;
                cleanup();
                resolve(message.message as Message);
                return;
              } else if (message.type === "error") {
                done = true;
                cleanup();
                reject(new Error(message.error || "Unknown streaming error"));
                return;
              }
            } catch (err) {
              done = true;
              cleanup();
              reject(
                new Error(
                  `Failed to parse streaming response: ${err instanceof Error ? err.message : String(err)}`,
                ),
              );
              return;
            }
          }

          newlineIndex = buffer.indexOf("\n");
        }
      });

      socket.on("error", (err) => {
        cleanup();
        reject(new Error(`Socket error: ${err.message}`));
      });

      socket.on("end", () => {
        if (!done) {
          cleanup();
          reject(new Error("Streaming ended before completion"));
        }
      });

      socket.connect(socketPath, () => {
        socket.write(
          JSON.stringify({
            action: "chat_stream",
            provider: providerId,
            messages,
          }),
        );
        socket.end();
      });
    });
  }
}
