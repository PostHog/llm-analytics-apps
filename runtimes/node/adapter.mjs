#!/usr/bin/env node

import fs from "fs";
import os from "os";
import path from "path";
import net from "net";
import { randomUUID } from "crypto";
import { createRequire } from "module";
import { fileURLToPath, pathToFileURL } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const CLI_ROOT = path.resolve(__dirname, "../..");
const LEGACY_NODE_ROOT = path.join(CLI_ROOT, "node");
const PROVIDERS_ROOT = path.join(LEGACY_NODE_ROOT, "dist", "providers");
const SOCKET_PATH = path.join(CLI_ROOT, "runtimes", "node", "adapter.sock");

const requireFromLegacyNode = createRequire(
  path.join(LEGACY_NODE_ROOT, "package.json"),
);
const { PostHog } = requireFromLegacyNode("posthog-node");

const enableSessionId = ["true", "1", "yes"].includes(
  String(process.env.ENABLE_AI_SESSION_ID || "True").toLowerCase(),
);
const aiSessionId = enableSessionId ? randomUUID() : null;

const posthog = new PostHog(process.env.POSTHOG_API_KEY, {
  host: process.env.POSTHOG_HOST || "https://app.posthog.com",
  flushAt: 1,
  flushInterval: 0,
});

const providerDefinitions = [
  {
    id: "anthropic",
    name: "Anthropic",
    moduleFile: "anthropic.js",
    className: "AnthropicProvider",
    streamingModuleFile: "anthropic-streaming.js",
    streamingClassName: "AnthropicStreamingProvider",
    inputModes: ["text", "image", "file"],
    options: [
      {
        id: "streaming",
        name: "Streaming",
        shortcutKey: "s",
        type: "boolean",
        default: false,
      },
      {
        id: "thinking",
        name: "Extended Thinking",
        shortcutKey: "t",
        type: "boolean",
        default: false,
      },
    ],
  },
  {
    id: "gemini",
    name: "Google Gemini",
    moduleFile: "gemini.js",
    className: "GeminiProvider",
    inputModes: ["text", "image", "file"],
    streamingModuleFile: "gemini-streaming.js",
    streamingClassName: "GeminiStreamingProvider",
    options: [
      {
        id: "streaming",
        name: "Streaming",
        shortcutKey: "s",
        type: "boolean",
        default: false,
      },
    ],
  },
  {
    id: "openai_responses",
    name: "OpenAI Responses",
    moduleFile: "openai.js",
    className: "OpenAIProvider",
    inputModes: ["text", "image", "file"],
    streamingModuleFile: "openai-streaming.js",
    streamingClassName: "OpenAIStreamingProvider",
    options: [
      {
        id: "streaming",
        name: "Streaming",
        shortcutKey: "s",
        type: "boolean",
        default: false,
      },
    ],
  },
  {
    id: "openai_chat",
    name: "OpenAI Chat Completions",
    moduleFile: "openai-chat.js",
    className: "OpenAIChatProvider",
    inputModes: ["text", "image", "file"],
    streamingModuleFile: "openai-chat-streaming.js",
    streamingClassName: "OpenAIChatStreamingProvider",
    options: [
      {
        id: "streaming",
        name: "Streaming",
        shortcutKey: "s",
        type: "boolean",
        default: true,
      },
    ],
  },
  {
    id: "openai_transcription",
    name: "OpenAI Transcriptions",
    moduleFile: "openai-transcription.js",
    className: "OpenAITranscriptionProvider",
    inputModes: ["audio", "file"],
  },
  {
    id: "openai_image",
    name: "OpenAI Image Generation",
    moduleFile: "openai-image.js",
    className: "OpenAIImageProvider",
    inputModes: ["text"],
  },
  {
    id: "gemini_image",
    name: "Gemini Image Generation",
    moduleFile: "gemini-image.js",
    className: "GeminiImageProvider",
    inputModes: ["text"],
  },
  {
    id: "langchain_openai",
    name: "LangChain (OpenAI)",
    moduleFile: "langchain.js",
    className: "LangChainProvider",
    inputModes: ["text"],
  },
  {
    id: "mastra_openai",
    name: "Mastra (OpenAI)",
    moduleFile: "mastra.js",
    className: "MastraProvider",
    inputModes: ["text"],
  },
  {
    id: "vercel_ai_openai",
    name: "Vercel AI SDK (OpenAI)",
    moduleFile: "vercel-ai.js",
    className: "VercelAIProvider",
    streamingModuleFile: "vercel-ai-streaming.js",
    streamingClassName: "VercelAIStreamingProvider",
    inputModes: ["text", "image", "file"],
    options: [
      {
        id: "streaming",
        name: "Streaming",
        shortcutKey: "s",
        type: "boolean",
        default: false,
      },
    ],
  },
  {
    id: "vercel_ai_google",
    name: "Vercel AI SDK (Google)",
    moduleFile: "vercel-ai-google.js",
    className: "VercelAIGoogleProvider",
    streamingModuleFile: "vercel-ai-google-streaming.js",
    streamingClassName: "VercelAIGoogleStreamingProvider",
    inputModes: ["text", "image", "file"],
    options: [
      {
        id: "streaming",
        name: "Streaming",
        shortcutKey: "s",
        type: "boolean",
        default: false,
      },
    ],
  },
  {
    id: "vercel_ai_anthropic",
    name: "Vercel AI SDK (Anthropic)",
    moduleFile: "vercel-ai-anthropic.js",
    className: "VercelAIAnthropicProvider",
    streamingModuleFile: "vercel-ai-anthropic-streaming.js",
    streamingClassName: "VercelAIAnthropicStreamingProvider",
    inputModes: ["text", "image", "file"],
    options: [
      {
        id: "streaming",
        name: "Streaming",
        shortcutKey: "s",
        type: "boolean",
        default: false,
      },
    ],
  },
  {
    id: "vercel_ai_gateway_anthropic",
    name: "Vercel AI Gateway (Anthropic)",
    moduleFile: "vercel-ai-gateway-anthropic.js",
    className: "VercelAIGatewayAnthropicProvider",
    streamingModuleFile: "vercel-ai-gateway-anthropic-streaming.js",
    streamingClassName: "VercelAIGatewayAnthropicStreamingProvider",
    inputModes: ["text", "image", "file"],
    options: [
      {
        id: "streaming",
        name: "Streaming",
        shortcutKey: "s",
        type: "boolean",
        default: false,
      },
    ],
  },
  {
    id: "vercel_generate_object",
    name: "Vercel AI SDK - generateObject (OpenAI)",
    moduleFile: "vercel-generate-object.js",
    className: "VercelGenerateObjectProvider",
    inputModes: ["text", "image", "file"],
  },
  {
    id: "vercel_stream_object",
    name: "Vercel AI SDK - streamObject (OpenAI)",
    moduleFile: "vercel-stream-object.js",
    className: "VercelStreamObjectProvider",
    streamingModuleFile: "vercel-stream-object.js",
    streamingClassName: "VercelStreamObjectProvider",
    inputModes: ["text", "image", "file"],
    options: [
      {
        id: "streaming",
        name: "Streaming",
        shortcutKey: "s",
        type: "boolean",
        default: true,
      },
    ],
  },
];

const providerOptions = new Map();
const providerInstances = new Map();

for (const def of providerDefinitions) {
  const defaults = {};
  for (const option of def.options || []) {
    defaults[option.id] = option.default;
  }
  providerOptions.set(def.id, defaults);
}

function getProviderDefinition(providerId) {
  const definition = providerDefinitions.find((def) => def.id === providerId);
  if (!definition) {
    throw new Error(`Unknown provider: ${providerId}`);
  }
  return definition;
}

async function instantiateProvider(providerId, forceStreaming = false) {
  const definition = getProviderDefinition(providerId);
  const options = providerOptions.get(providerId) || {};
  const useStreaming =
    (forceStreaming || Boolean(options.streaming)) &&
    definition.streamingModuleFile &&
    definition.streamingClassName;

  const moduleFile = useStreaming
    ? definition.streamingModuleFile
    : definition.moduleFile;
  const className = useStreaming
    ? definition.streamingClassName
    : definition.className;

  const modulePath = path.join(PROVIDERS_ROOT, moduleFile);
  const providerModule = await import(pathToFileURL(modulePath).href);
  const ProviderClass = providerModule[className];

  if (!ProviderClass) {
    throw new Error(
      `Provider class "${className}" not found in ${moduleFile}`,
    );
  }

  if (providerId.startsWith("anthropic")) {
    return new ProviderClass(posthog, Boolean(options.thinking), undefined, aiSessionId);
  }

  return new ProviderClass(posthog, aiSessionId);
}

async function getProvider(providerId) {
  const cached = providerInstances.get(providerId);
  if (cached) {
    return cached;
  }

  const instance = await instantiateProvider(providerId);
  providerInstances.set(providerId, instance);
  return instance;
}

async function getStreamingProvider(providerId) {
  const definition = getProviderDefinition(providerId);
  if (!definition.streamingModuleFile || !definition.streamingClassName) {
    return getProvider(providerId);
  }

  return instantiateProvider(providerId, true);
}

function getLatestUserInput(messages) {
  const userMessage = [...messages].reverse().find((msg) => msg.role === "user");
  if (!userMessage) {
    return { text: "Hello!", imageBase64: undefined };
  }

  const textParts = [];
  let imageBase64;

  for (const block of userMessage.content || []) {
    if (block.type === "text" && block.text) {
      textParts.push(block.text);
      continue;
    }

    if (imageBase64) {
      continue;
    }

    if (
      block.type === "image" ||
      (block.type === "file" &&
        typeof block.mimeType === "string" &&
        block.mimeType.startsWith("image/"))
    ) {
      try {
        const bytes = fs.readFileSync(block.path);
        imageBase64 = bytes.toString("base64");
      } catch (err) {
        console.error(`Failed to read image file ${block.path}:`, err);
      }
    }
  }

  const text = textParts.join("\n").trim() || "Please describe this image.";
  return { text, imageBase64 };
}

function createTextMessage(text) {
  return {
    role: "assistant",
    content: [{ type: "text", text }],
  };
}

async function runModeTest(providerId, mode) {
  const provider = await getProvider(providerId);

  if (typeof provider.resetConversation === "function") {
    provider.resetConversation();
  }

  if (mode === "tool_call_test") {
    const response = await provider.chat("What is the weather in Montreal, Canada?");
    return createTextMessage(response);
  }

  if (mode === "message_test") {
    const response = await provider.chat("Hi, how are you today?");
    return createTextMessage(response);
  }

  if (mode === "image_test") {
    const base64Image =
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==";
    const response = await provider.chat(
      "What do you see in this image? Please describe it.",
      base64Image,
    );
    return createTextMessage(response);
  }

  if (mode === "embeddings_test") {
    if (typeof provider.embed !== "function") {
      return createTextMessage(`Provider ${providerId} does not support embeddings.`);
    }
    const embedding = await provider.embed("The quick brown fox jumps over the lazy dog.");
    const sample = Array.isArray(embedding) ? embedding.slice(0, 5).join(", ") : "";
    return createTextMessage(
      `Embedding generated (${embedding?.length || 0} dimensions). Sample: [${sample}]`,
    );
  }

  if (mode === "structured_output_test") {
    const response = await provider.chat(
      "Create a profile for a 25-year-old software developer who loves hiking and photography.",
    );
    return createTextMessage(response);
  }

  if (mode === "transcription_test") {
    if (typeof provider.transcribe !== "function") {
      return createTextMessage(`Provider ${providerId} does not support transcription.`);
    }
    const audioPath = path.join(CLI_ROOT, "test-audio.mp3");
    if (!fs.existsSync(audioPath)) {
      return createTextMessage(`Test audio file not found: ${audioPath}`);
    }
    const text = await provider.transcribe(audioPath);
    return createTextMessage(text || "No transcription generated.");
  }

  if (mode === "image_generation_test") {
    if (typeof provider.generateImage !== "function") {
      return createTextMessage(`Provider ${providerId} does not support image generation.`);
    }
    const imageResult = await provider.generateImage(
      "A serene mountain landscape at sunset with a lake reflection",
    );
    return createTextMessage(imageResult || "No image result returned.");
  }

  return createTextMessage(`Unknown mode: ${mode}`);
}

async function handleMessage(rawData) {
  const data = JSON.parse(rawData.toString("utf-8"));
  const action = data.action;

  if (action === "get_providers") {
    return {
      providers: providerDefinitions.map((provider) => ({
        id: provider.id,
        name: provider.name,
        options: provider.options || [],
        input_modes: provider.inputModes,
      })),
    };
  }

  if (action === "set_provider_option") {
    const { provider, option_id, value } = data;
    const definition = getProviderDefinition(provider);
    const optionDef = (definition.options || []).find((opt) => opt.id === option_id);

    if (!optionDef) {
      throw new Error(`Unknown option "${option_id}" for provider "${provider}"`);
    }

    const options = providerOptions.get(provider) || {};
    options[option_id] = value;
    providerOptions.set(provider, options);
    providerInstances.delete(provider);

    return { success: true };
  }

  if (action === "chat") {
    const providerId = data.provider;
    const messages = data.messages || [];

    const provider = await getProvider(providerId);
    const { text, imageBase64 } = getLatestUserInput(messages);

    let responseText = "";

    if (typeof provider.chatStream === "function" && !imageBase64) {
      for await (const chunk of provider.chatStream(text)) {
        responseText += chunk;
      }
    } else {
      responseText = await provider.chat(text, imageBase64);
    }

    return {
      message: {
        role: "assistant",
        content: [{ type: "text", text: responseText }],
      },
    };
  }

  if (action === "run_mode_test") {
    const providerId = data.provider;
    const mode = data.mode;
    const message = await runModeTest(providerId, mode);
    return { message };
  }

  throw new Error(`Unknown action: ${action}`);
}

async function handleStreamingRequest(conn, data) {
  const providerId = data.provider;
  const messages = data.messages || [];

  const provider = await getStreamingProvider(providerId);
  const { text, imageBase64 } = getLatestUserInput(messages);

  let responseText = "";

  if (typeof provider.chatStream === "function" && !imageBase64) {
    for await (const chunk of provider.chatStream(text)) {
      responseText += chunk;
      conn.write(JSON.stringify({ type: "chunk", chunk }) + "\n");
    }
  } else {
    responseText = await provider.chat(text, imageBase64);
    conn.write(JSON.stringify({ type: "chunk", chunk: responseText }) + "\n");
  }

  conn.write(
    JSON.stringify({
      type: "done",
      message: {
        role: "assistant",
        content: [{ type: "text", text: responseText }],
      },
    }) + "\n",
  );
}

try {
  fs.mkdirSync(path.dirname(SOCKET_PATH), { recursive: true });
  if (fs.existsSync(SOCKET_PATH)) {
    fs.unlinkSync(SOCKET_PATH);
  }

  const server = net.createServer({ allowHalfOpen: true }, (conn) => {
    let data = "";

    conn.on("data", (chunk) => {
      data += chunk.toString();
    });

    conn.on("end", async () => {
      if (!data.trim()) {
        conn.write(JSON.stringify({ error: "Empty request payload" }));
        conn.end();
        return;
      }

      try {
        const parsed = JSON.parse(data);
        if (parsed.action === "chat_stream") {
          await handleStreamingRequest(conn, parsed);
        } else {
          const response = await handleMessage(data);
          conn.write(JSON.stringify(response));
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        if (data.includes('"action":"chat_stream"')) {
          conn.write(JSON.stringify({ type: "error", error: message }) + "\n");
        } else {
          conn.write(JSON.stringify({ error: message }));
        }
      } finally {
        conn.end();
      }
    });

    conn.on("error", (err) => {
      console.error("Connection error:", err);
    });
  });

  server.listen(SOCKET_PATH, () => {
    console.error(`Node runtime listening on ${SOCKET_PATH}`);
  });

  const shutdown = () => {
    try {
      server.close();
    } finally {
      try {
        posthog.shutdown();
      } catch {
        // no-op
      }
      if (fs.existsSync(SOCKET_PATH)) {
        fs.unlinkSync(SOCKET_PATH);
      }
      process.exit(0);
    }
  };

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
} catch (err) {
  console.error(err);
  process.exit(1);
}
