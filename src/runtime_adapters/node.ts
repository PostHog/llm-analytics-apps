import { exec } from "child_process";
import { promisify } from "util";
import path from "path";
import fs from "fs/promises";
import { Socket } from "net";
import SubprocessAdapter from "./utils/subprocess.js";
import type { Message, Provider } from "../types.js";

const execAsync = promisify(exec);

const NODE_RUNTIME_DIR = path.join(process.cwd(), "runtimes", "node");
const LEGACY_NODE_DIR = path.join(process.cwd(), "node");

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
    const adapterPath = path.join(NODE_RUNTIME_DIR, "adapter.mjs");
    return { command: "node", args: [adapterPath] };
  }

  async ensureRuntimeSetup(): Promise<void> {
    const providersBuildOutput = path.join(
      LEGACY_NODE_DIR,
      "dist",
      "providers",
      "base.js",
    );
    const providersSourceDir = path.join(LEGACY_NODE_DIR, "src", "providers");

    const buildExists = await fs
      .access(providersBuildOutput)
      .then(() => true)
      .catch(() => false);

    let shouldBuild = !buildExists;

    if (!shouldBuild) {
      const [distStat, srcEntries] = await Promise.all([
        fs.stat(providersBuildOutput),
        fs.readdir(providersSourceDir),
      ]);
      const srcFiles = srcEntries.filter((entry) => entry.endsWith(".ts"));
      const srcStats = await Promise.all(
        srcFiles.map((file) => fs.stat(path.join(providersSourceDir, file))),
      );
      shouldBuild = srcStats.some((stat) => stat.mtimeMs > distStat.mtimeMs);
    }

    if (shouldBuild) {
      console.log("Building Node providers...");
      try {
        await execAsync(`pnpm --dir "${LEGACY_NODE_DIR}" build`);
      } catch (err) {
        throw new Error(
          `Failed to build legacy Node providers: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    }
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
