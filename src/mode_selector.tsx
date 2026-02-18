import SelectInput from "ink-select-input";
import { useNavigateScreen, type Screen } from "./screen_context.js";
import { Box, Text, useApp } from "ink";
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

const Indicator = ({ isSelected = false }: { isSelected?: boolean }) => (
  <Box marginRight={1}>
    <Text color={isSelected ? "#B62AD9" : "gray"}>
      {isSelected ? "\u25B8" : " "}
    </Text>
  </Box>
);

export function ModeSelector() {
  const navigate = useNavigateScreen();
  const app = useApp();
  const { runtime } = useRuntime();
  const { setMode } = useMode();
  const { provider } = useProvider();
  const { optionValues } = useOptions();
  const providerId = provider.id;
  const runtimeId = runtime.id();
  const providerInputModes = new Set(provider.input_modes);
  const openAIEndpoint =
    typeof optionValues["endpoint"] === "string"
      ? optionValues["endpoint"]
      : "";

  const supportsChat = ![
    "openai_transcription",
    "openai_image",
    "gemini_image",
  ].includes(providerId);
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
      reason:
        "Unavailable: current provider/model does not support chat tests.",
    },
    {
      label: "Message Test",
      value: "mode_runner",
      mode: "message_test",
      enabled: supportsChat,
      reason:
        "Unavailable: current provider/model does not support chat tests.",
    },
    {
      label: "Image Test",
      value: "mode_runner",
      mode: "image_test",
      enabled: supportsChat && supportsImageInput,
      reason:
        "Unavailable: current provider/model does not support image input.",
    },
    {
      label: "Embeddings Test",
      value: "mode_runner",
      mode: "embeddings_test",
      enabled: supportsEmbeddings,
      reason:
        "Unavailable: current provider/model does not support embeddings.",
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

  const visibleItems = items.filter((item) => item.enabled !== false);

  const ItemComponent = ({
    isSelected = false,
    label = "",
  }: {
    isSelected?: boolean;
    label?: string;
  }) => {
    if (label === "Exit") {
      return (
        <Text color={isSelected ? "red" : "gray"} bold={isSelected}>
          {label}
        </Text>
      );
    }
    return (
      <Text color="white" bold={isSelected} dimColor={!isSelected}>
        {label}
      </Text>
    );
  };

  return (
    <Box flexDirection="column" padding={1}>
      <Box borderStyle="bold" borderColor="#B62AD9" paddingX={2}>
        <Text bold color="#B62AD9">
          {"\u25A0"} PostHog LLM Analytics
        </Text>
      </Box>

      <Box marginTop={1} marginLeft={1} marginBottom={1}>
        <Text bold>Select a mode</Text>
      </Box>

      <SelectInput
        items={visibleItems}
        onSelect={handleSelect}
        indicatorComponent={Indicator}
        itemComponent={ItemComponent}
      />
    </Box>
  );
}
