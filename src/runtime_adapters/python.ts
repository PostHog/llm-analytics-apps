import { exec } from "child_process";
import { promisify } from "util";
import path from "path";
import fs from "fs/promises";
import SubprocessAdapter from "./utils/subprocess.js";
import type { Message, Provider, RuntimeTool } from "../types.js";

const execAsync = promisify(exec);

const PYTHON_RUNTIME_DIR = path.join(process.cwd(), "runtimes", "python");
const DEFAULT_VENV_DIR = path.join(PYTHON_RUNTIME_DIR, "venv");
const VENV_DIR =
  process.env["LLM_ANALYTICS_PYTHON_VENV"] || DEFAULT_VENV_DIR;
const UV_CACHE_DIR = path.join(PYTHON_RUNTIME_DIR, ".uv-cache");
const PYTHON_DEPS_CONFIG_PATH = path.join(PYTHON_RUNTIME_DIR, ".deps-config.json");
const LOG_DIR = path.join(process.cwd(), ".logs");
const PYTHON_SETUP_LOG_PATH = path.join(LOG_DIR, "runtime-python-setup.log");

type PythonDepsConfig =
  | { mode: "default"; litellmPath?: string }
  | { mode: "local"; pythonPath: string; litellmPath?: string }
  | { mode: "version"; pythonVersion: string; litellmPath?: string };

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
        await this.logSetup("Creating Python virtual environment...");
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
        "import posthog, openai, anthropic, dotenv, google.genai, requests, langchain, litellm, opentelemetry";
      const dependenciesInstalled = await execAsync(
        `"${pythonPath}" -c "${dependencyCheck}"`,
      )
        .then(() => true)
        .catch(() => false);

      if (!dependenciesInstalled) {
        await this.logSetup("Installing Python dependencies...");
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

      await this.ensurePostHogPythonDependencyMode(pythonPath);
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

  private getDesiredDepsConfig(): PythonDepsConfig {
    const litellmPath = process.env["LITELLM_PATH"]?.trim();
    const localPath = process.env["POSTHOG_PYTHON_PATH"]?.trim();
    if (localPath) {
      const config: PythonDepsConfig = { mode: "local", pythonPath: localPath };
      if (litellmPath) {
        config.litellmPath = litellmPath;
      }
      return config;
    }

    const version = process.env["POSTHOG_PYTHON_VERSION"]?.trim();
    if (version) {
      const config: PythonDepsConfig = { mode: "version", pythonVersion: version };
      if (litellmPath) {
        config.litellmPath = litellmPath;
      }
      return config;
    }

    if (litellmPath) {
      return { mode: "default", litellmPath };
    }
    return { mode: "default" };
  }

  private async readAppliedDepsConfig(): Promise<PythonDepsConfig | null> {
    try {
      const raw = await fs.readFile(PYTHON_DEPS_CONFIG_PATH, "utf8");
      return JSON.parse(raw) as PythonDepsConfig;
    } catch {
      return null;
    }
  }

  private async writeAppliedDepsConfig(config: PythonDepsConfig): Promise<void> {
    await fs.mkdir(PYTHON_RUNTIME_DIR, { recursive: true });
    await fs.writeFile(
      PYTHON_DEPS_CONFIG_PATH,
      JSON.stringify(config, null, 2),
      "utf8",
    );
  }

  private async ensurePostHogPythonDependencyMode(
    pythonPath: string,
  ): Promise<void> {
    const desired = this.getDesiredDepsConfig();
    const applied = await this.readAppliedDepsConfig();

    if (JSON.stringify(desired) === JSON.stringify(applied)) {
      return;
    }

    await fs.mkdir(UV_CACHE_DIR, { recursive: true });

    if (desired.mode === "local") {
      const absolutePath = path.resolve(process.cwd(), desired.pythonPath);
      const packageExists = await fs
        .access(path.join(absolutePath, "pyproject.toml"))
        .then(() => true)
        .catch(() => false);
      if (!packageExists) {
        throw new Error(
          `POSTHOG_PYTHON_PATH is set but invalid: ${absolutePath}. Expected to find pyproject.toml in that directory.`,
        );
      }
      console.log(
        `Overriding with local posthog-python from ${desired.pythonPath}...`,
      );
      await this.logSetup(
        `Overriding with local posthog-python from ${desired.pythonPath}.`,
      );
      await execAsync(
        `UV_CACHE_DIR="${UV_CACHE_DIR}" uv pip install --python "${pythonPath}" -e "${absolutePath}"`,
      );
      await this.ensureLiteLLMMode(pythonPath, desired, applied);
      await this.writeAppliedDepsConfig(desired);
      return;
    }

    if (desired.mode === "version") {
      console.log(
        `Installing posthog==${desired.pythonVersion} in Python runtime...`,
      );
      await this.logSetup(
        `Installing posthog==${desired.pythonVersion} in Python runtime.`,
      );
      await execAsync(
        `UV_CACHE_DIR="${UV_CACHE_DIR}" uv pip install --python "${pythonPath}" "posthog==${desired.pythonVersion}"`,
      );
      await this.ensureLiteLLMMode(pythonPath, desired, applied);
      await this.writeAppliedDepsConfig(desired);
      return;
    }

    if (applied && applied.mode !== "default") {
      await this.logSetup("Restoring default posthog package in Python runtime.");
      await execAsync(
        `UV_CACHE_DIR="${UV_CACHE_DIR}" uv pip install --python "${pythonPath}" --upgrade posthog`,
      );
    }

    await this.ensureLiteLLMMode(pythonPath, desired, applied);
    await this.writeAppliedDepsConfig(desired);
  }

  private async ensureLiteLLMMode(
    pythonPath: string,
    desired: PythonDepsConfig,
    applied: PythonDepsConfig | null,
  ): Promise<void> {
    const desiredLiteLLMPath = desired.litellmPath?.trim();
    const appliedLiteLLMPath = applied?.litellmPath?.trim();

    if (desiredLiteLLMPath === appliedLiteLLMPath) {
      return;
    }

    if (desiredLiteLLMPath) {
      const absolutePath = path.resolve(process.cwd(), desiredLiteLLMPath);
      const packageExists = await fs
        .access(path.join(absolutePath, "pyproject.toml"))
        .then(() => true)
        .catch(() => false);
      if (!packageExists) {
        throw new Error(
          `LITELLM_PATH is set but invalid: ${absolutePath}. Expected to find pyproject.toml in that directory.`,
        );
      }

      console.log(`Overriding with local LiteLLM from ${desiredLiteLLMPath}...`);
      await this.logSetup(
        `Overriding with local LiteLLM from ${desiredLiteLLMPath}.`,
      );
      await execAsync(
        `UV_CACHE_DIR="${UV_CACHE_DIR}" uv pip install --python "${pythonPath}" -e "${absolutePath}"`,
      );
      return;
    }

    if (appliedLiteLLMPath) {
      await this.logSetup("Restoring default litellm package in Python runtime.");
      await execAsync(
        `UV_CACHE_DIR="${UV_CACHE_DIR}" uv pip install --python "${pythonPath}" --upgrade litellm`,
      );
    }
  }

  private async logSetup(message: string): Promise<void> {
    const line = `[${new Date().toISOString()}] ${message}\n`;
    await fs.mkdir(LOG_DIR, { recursive: true });
    await fs.appendFile(PYTHON_SETUP_LOG_PATH, line, "utf8");
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
}
