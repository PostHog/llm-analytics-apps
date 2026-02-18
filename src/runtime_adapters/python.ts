import { exec } from "child_process";
import { promisify } from "util";
import path from "path";
import fs from "fs/promises";
import { existsSync } from "fs";
import SubprocessAdapter from "./utils/subprocess.js";
import type { Message, Provider } from "../types.js";

const execAsync = promisify(exec);

const PYTHON_RUNTIME_DIR = path.join(process.cwd(), "runtimes", "python");
const DEFAULT_VENV_DIR = path.join(PYTHON_RUNTIME_DIR, "venv");
const SHARED_VENV_DIR = path.join(process.cwd(), "python", "venv");
const VENV_DIR =
  process.env["LLM_ANALYTICS_PYTHON_VENV"] ||
  (existsSync(SHARED_VENV_DIR) ? SHARED_VENV_DIR : DEFAULT_VENV_DIR);
const UV_CACHE_DIR = path.join(PYTHON_RUNTIME_DIR, ".uv-cache");

export default class PythonAdapter extends SubprocessAdapter {
  override id(): string {
    return "python";
  }

  override name(): string {
    return "Python";
  }

  getSocketPath(): string {
    return "/tmp/llm-analytics-python.sock";
  }

  getCommand(): { command: string; args: string[] } {
    const pythonPath = path.join(VENV_DIR, "bin", "python3");
    const adapterPath = path.join(PYTHON_RUNTIME_DIR, "adapter.py");
    return { command: pythonPath, args: [adapterPath] };
  }

  /**
   * Ensure Python environment is set up
   */
  async ensureRuntimeSetup(): Promise<void> {
    try {
      // Check if venv exists
      const venvExists = await fs
        .access(VENV_DIR)
        .then(() => true)
        .catch(() => false);

      if (!venvExists) {
        console.log("Creating Python virtual environment...");
        try {
          await fs.mkdir(UV_CACHE_DIR, { recursive: true });
          await execAsync(
            `UV_CACHE_DIR="${UV_CACHE_DIR}" uv venv "${VENV_DIR}"`,
          );
        } catch (err) {
          throw new Error(
            `Failed to create Python virtual environment: ${err instanceof Error ? err.message : String(err)}`,
          );
        }
      }
      const pythonPath = path.join(VENV_DIR, "bin", "python3");

      // Only install dependencies if required modules are missing.
      const dependencyCheck =
        "import posthog, openai, anthropic, dotenv, google.genai";
      const dependenciesInstalled = await execAsync(
        `"${pythonPath}" -c "${dependencyCheck}"`,
      )
        .then(() => true)
        .catch(() => false);

      if (!dependenciesInstalled) {
        console.log("Installing Python dependencies...");
        const requirementsPath = path.join(
          PYTHON_RUNTIME_DIR,
          "requirements.txt",
        );
        try {
          await fs.mkdir(UV_CACHE_DIR, { recursive: true });
          await execAsync(
            `UV_CACHE_DIR="${UV_CACHE_DIR}" uv pip install --python "${pythonPath}" -r "${requirementsPath}"`,
          );
        } catch (err) {
          throw new Error(
            `Failed to install Python dependencies: ${err instanceof Error ? err.message : String(err)}`,
          );
        }
      }

      // Check for local posthog-python path from environment
      const posthogPythonPath = process.env["POSTHOG_PYTHON_PATH"];

      // Install local posthog-python last (replaces PyPI version)
      if (posthogPythonPath) {
        const absolutePath = path.resolve(process.cwd(), posthogPythonPath);

        const installedFromLocalPath = await execAsync(
          `"${pythonPath}" -c "import pathlib, posthog; print(pathlib.Path(posthog.__file__).resolve())"`,
        )
          .then(({ stdout }) => stdout.trim().startsWith(absolutePath))
          .catch(() => false);

        if (!installedFromLocalPath) {
          console.log(
            `Overriding with local posthog-python from ${posthogPythonPath}...`,
          );
          try {
            await fs.mkdir(UV_CACHE_DIR, { recursive: true });
            await execAsync(
              `UV_CACHE_DIR="${UV_CACHE_DIR}" uv pip install --python "${pythonPath}" -e "${absolutePath}"`,
            );
          } catch (err) {
            console.warn(
              `Warning: failed to install local posthog-python (${err instanceof Error ? err.message : String(err)}). Continuing with existing posthog package.`,
            );
          }
        }
      }
    } catch (err) {
      // Re-throw if already a formatted error
      if (err instanceof Error && err.message.startsWith("Failed to")) {
        throw err;
      }
      throw new Error(
        `Python runtime setup failed: ${err instanceof Error ? err.message : String(err)}`,
      );
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
}
