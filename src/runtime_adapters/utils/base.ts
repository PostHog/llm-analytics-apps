import type { Message, Provider, RuntimeTool } from "../../types.js";

export default abstract class RuntimeAdapter {
  abstract id(): string;
  name(): string {
    return this.id();
  }

  /**
   * Start the runtime (setup, spawn processes, etc.)
   * Called when runtime is selected
   */
  async start(): Promise<void> {
    // Default: no-op for runtimes that don't need startup
  }

  /**
   * Stop the runtime (cleanup, kill processes, etc.)
   * Called when switching away from this runtime
   */
  async stop(): Promise<void> {
    // Default: no-op for runtimes that don't need cleanup
  }

  /**
   * Get the list of providers supported by this runtime
   * @returns Array of providers with id, name, and options
   */
  abstract getProviders(): Promise<Provider[]>;

  /**
   * Set a provider option value
   * @param providerId - ID of the provider
   * @param optionId - ID of the option to set
   * @param value - New value for the option
   */
  abstract setProviderOption(
    providerId: string,
    optionId: string,
    value: string | boolean,
  ): Promise<void>;

  /**
   * Send a chat message and get a response
   * @param providerId - ID of the provider to use
   * @param messages - Conversation history in unified format
   * @returns Response message from the LLM in unified format
   */
  abstract chat(providerId: string, messages: Message[]): Promise<Message>;

  /**
   * Optional streaming chat path.
   * Runtimes that support incremental output can implement this and emit chunks via onChunk.
   */
  chatStream?(
    _providerId: string,
    _messages: Message[],
    _onChunk: (chunk: string) => void,
  ): Promise<Message>;

  abstract runModeTest(providerId: string, mode: string): Promise<Message>;

  /**
   * Runtime-specific utility tools surfaced in the CLI.
   */
  async getTools(): Promise<RuntimeTool[]> {
    return [];
  }

  /**
   * Execute a runtime-specific utility tool and return its output as a message.
   */
  async runTool(_toolId: string, _providerId?: string): Promise<Message> {
    throw new Error(`Runtime ${this.name()} does not support tools`);
  }
}
