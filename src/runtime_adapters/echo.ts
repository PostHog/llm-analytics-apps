import RuntimeAdapter from "./utils/base.js";
import type { Message, Provider } from "../types.js";

export default class EchoAdapter extends RuntimeAdapter {
  id(): string {
    return "echo";
  }

  override name(): string {
    return "~(Debug) Echo";
  }

  async getProviders(): Promise<Provider[]> {
    return [
      { id: "echo", name: "Echo Provider", input_modes: ["text", "file"] },
    ];
  }

  async setProviderOption(
    _providerId: string,
    _optionId: string,
    _value: string | boolean,
  ): Promise<void> {
    // Echo provider has no options, so this is a no-op
  }

  async chat(_providerId: string, messages: Message[]): Promise<Message> {
    const lastUserMessage = messages.filter((msg) => msg.role === "user").pop();

    if (!lastUserMessage) {
      return {
        role: "assistant",
        content: [{ type: "text", text: "No user message found." }],
      };
    }

    const textBlocks = lastUserMessage.content
      .filter((block) => block.type === "text")
      .map((block) => block.text);

    const fileBlocks = lastUserMessage.content.filter(
      (block) => block.type === "file",
    );

    const userText = textBlocks.join(" ");
    let responseText = userText
      ? `You said: ${userText}`
      : "You sent a message";

    if (fileBlocks.length > 0) {
      const fileCount = fileBlocks.length;
      const fileText = fileCount === 1 ? "1 file" : `${fileCount} files`;
      responseText += `. You also attached ${fileText}`;
    }

    return {
      role: "assistant",
      content: [{ type: "text", text: responseText }],
    };
  }

  async runModeTest(providerId: string, _mode: string): Promise<Message> {
    return this.chat(providerId, [
      { role: "user", content: [{ type: "text", text: "echo mode test" }] },
    ]);
  }
}
