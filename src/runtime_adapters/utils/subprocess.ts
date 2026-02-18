import { spawn, type ChildProcess } from "child_process";
import { Socket } from "net";
import fs from "fs/promises";
import RuntimeAdapter from "./base.js";

/**
 * Base class for runtimes that run in a subprocess and communicate via Unix socket + JSON
 */
export default abstract class SubprocessAdapter extends RuntimeAdapter {
  #process?: ChildProcess;

  /**
   * Get the Unix socket path for this runtime
   */
  abstract getSocketPath(): string;

  /**
   * Get the command and args to spawn the subprocess
   */
  abstract getCommand(): { command: string; args: string[] };

  /**
   * Ensure the runtime environment is set up (venvs, dependencies, etc.)
   */
  abstract ensureRuntimeSetup(): Promise<void>;

  /**
   * Start the subprocess runtime
   */
  override async start(): Promise<void> {
    await this.ensureRuntimeSetup();
    await this.#startProcess();
  }

  /**
   * Stop the subprocess runtime
   */
  override async stop(): Promise<void> {
    this.#process?.kill();

    // Remove socket file
    const socketPath = this.getSocketPath();
    try {
      await fs.unlink(socketPath);
    } catch {
      // Ignore errors
    }
  }

  /**
   * Send a JSON message to the subprocess and get a JSON response
   */
  async sendMessage<T = unknown>(message: unknown): Promise<T> {
    return new Promise((resolve, reject) => {
      const socketPath = this.getSocketPath();
      const socket = new Socket();
      const messageStr = JSON.stringify(message);
      let responseData = "";

      const onData = (data: Buffer) => {
        responseData += data.toString();
      };

      const onEnd = () => {
        socket.off("data", onData);
        socket.off("end", onEnd);
        socket.off("error", onError);
        socket.destroy();

        try {
          if (!responseData.trim()) {
            reject(new Error("Failed to parse response: empty response"));
            return;
          }

          const response = JSON.parse(responseData);
          if (response.error) {
            reject(new Error(response.error));
          } else {
            resolve(response);
          }
        } catch (err) {
          reject(new Error(`Failed to parse response: ${err}`));
        }
      };

      const onError = (err: Error) => {
        socket.off("data", onData);
        socket.off("end", onEnd);
        socket.off("error", onError);
        socket.destroy();
        reject(err);
      };

      socket.on("data", onData);
      socket.on("end", onEnd);
      socket.on("error", onError);

      socket.connect(socketPath, () => {
        socket.write(messageStr);
        socket.end();
      });
    });
  }

  /**
   * Start the subprocess
   */
  async #startProcess(): Promise<void> {
    const socketPath = this.getSocketPath();

    // Remove old socket if it exists
    try {
      await fs.unlink(socketPath);
    } catch {
      // Socket doesn't exist, that's fine
    }

    const { command, args } = this.getCommand();

    // Spawn process with inherited environment
    this.#process = spawn(command, args, {
      cwd: process.cwd(),
      stdio: ["ignore", "pipe", "pipe"],
      env: process.env,
    });

    // Capture errors
    let processError = "";

    // Log process output
    this.#process.stdout?.on("data", (data) => {
      console.log(`[${this.name()}] ${data.toString().trim()}`);
    });

    this.#process.stderr?.on("data", (data) => {
      const msg = data.toString().trim();
      console.error(`[${this.name()}] ${msg}`);
      processError += msg + "\n";
    });

    this.#process.on("exit", (code) => {
      if (code !== 0) {
        console.error(`[${this.name()}] Process exited with code ${code}`);
      }
    });

    // Wait for socket to be ready
    try {
      await this.#waitForSocket();
    } catch (err) {
      throw new Error(
        `${this.name()} adapter failed to start. ${processError ? `Error: ${processError}` : ""}`,
      );
    }

  }

  /**
   * Wait for the Unix socket to be created
   */
  async #waitForSocket(): Promise<void> {
    const socketPath = this.getSocketPath();
    const maxRetries = 50;
    const retryDelay = 100; // ms

    for (let i = 0; i < maxRetries; i++) {
      try {
        await fs.access(socketPath);
        return; // Socket exists
      } catch {
        await new Promise((resolve) => setTimeout(resolve, retryDelay));
      }
    }

    throw new Error(`${this.name()} adapter socket did not become ready`);
  }
}
