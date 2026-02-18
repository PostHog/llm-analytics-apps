import SelectInput from "ink-select-input";
import { useNavigateScreen, type Screen } from "./screen_context.js";
import { Box, Text, useApp } from "ink";
import { useState } from "react";
import { useRuntime } from "./runtime_context.js";
import { useMode, type AppMode } from "./mode_context.js";
import { useProvider } from "./provider_context.js";
import { useOptions } from "./option_context.js";

interface Item {
  label: string;
  value: Screen | "__exit__";
  mode?: AppMode;
  enabled?: boolean;
  reason?: string;
}

export function ModeSelector() {
  const navigate = useNavigateScreen();
  const app = useApp();
  const { runtime } = useRuntime();
  const { setMode } = useMode();
  const { provider } = useProvider();
  const { optionValues } = useOptions();
  const [hint, setHint] = useState<string>("");

  const providerId = provider.id;
  const runtimeId = runtime.id();
  const providerInputModes = new Set(provider.input_modes);
  const openAIEndpoint =
    typeof optionValues["endpoint"] === "string"
      ? optionValues["endpoint"]
      : "";

  const supportsChat = !["openai_transcription", "openai_image", "gemini_image"].includes(
    providerId,
  );
  const supportsImageInput = providerInputModes.has("image");
  const supportsEmbeddings = ["openai_chat", "openai_responses"].includes(
    providerId,
  );
  const supportsTranscription =
    providerId === "openai_transcription" ||
    (runtimeId === "python" &&
      providerId === "openai" &&
      openAIEndpoint === "audio_api_gpt4o_audio_preview");
  const supportsImageGeneration = ["openai_image", "gemini_image"].includes(
    providerId,
  );

  const handleSelect = async (item: Item) => {
    if (item.enabled === false) {
      setHint(item.reason || "This mode is unavailable for the current model.");
      return;
    }

    setHint("");

    if (item.value === "__exit__") {
      try {
        await runtime.stop();
      } catch {
        // Ignore cleanup errors while exiting.
      }
      app.exit();
      setImmediate(() => process.exit(0));
      return;
    }

    if (item.mode) {
      setMode(item.mode);
    }
    navigate(item.value);
  };

  const items: Item[] = [
    { label: "Chat mode", value: "chat", mode: "chat" },
    {
      label: "Tool Call Test",
      value: "mode_runner",
      mode: "tool_call_test",
      enabled: supportsChat,
      reason: "Unavailable: current provider/model does not support chat tests.",
    },
    {
      label: "Message Test",
      value: "mode_runner",
      mode: "message_test",
      enabled: supportsChat,
      reason: "Unavailable: current provider/model does not support chat tests.",
    },
    {
      label: "Image Test",
      value: "mode_runner",
      mode: "image_test",
      enabled: supportsChat && supportsImageInput,
      reason: "Unavailable: current provider/model does not support image input.",
    },
    {
      label: "Embeddings Test",
      value: "mode_runner",
      mode: "embeddings_test",
      enabled: supportsEmbeddings,
      reason: "Unavailable: current provider/model does not support embeddings.",
    },
    {
      label: "Structured Output Test",
      value: "mode_runner",
      mode: "structured_output_test",
      enabled: supportsChat,
      reason:
        "Unavailable: current provider/model does not support structured output test.",
    },
    {
      label: "Transcription Test",
      value: "mode_runner",
      mode: "transcription_test",
      enabled: supportsTranscription,
      reason:
        "Unavailable: use OpenAI Transcriptions provider (or supported audio endpoint).",
    },
    {
      label: "Image Generation Test",
      value: "mode_runner",
      mode: "image_generation_test",
      enabled: supportsImageGeneration,
      reason:
        "Unavailable: use an image generation provider (OpenAI/Gemini Image).",
    },
    { label: "Exit", value: "__exit__" },
  ];

  const renderedItems = items.map((item) => ({
    ...item,
    label: item.enabled === false ? `${item.label} (Unavailable)` : item.label,
  }));

  return (
    <Box padding={2} flexDirection="column">
      <SelectInput
        items={renderedItems}
        onSelect={handleSelect}
      />
      {hint ? (
        <Box marginTop={1}>
          <Text color="yellow">{hint}</Text>
        </Box>
      ) : null}
    </Box>
  );
}
