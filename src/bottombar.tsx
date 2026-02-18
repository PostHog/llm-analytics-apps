import { Box, Text, useStdout } from "ink";
import { useProvider } from "./provider_context.js";
import { useOptions } from "./option_context.js";
import { useScreen } from "./screen_context.js";
import { useMode } from "./mode_context.js";
import { useFocus } from "./focus_context.js";

const MODE_LABELS: Record<string, string> = {
  chat: "Chat",
  tool_call_test: "Tool Call Test",
  message_test: "Message Test",
  image_test: "Image Test",
  embeddings_test: "Embeddings Test",
  structured_output_test: "Structured Output Test",
  transcription_test: "Transcription Test",
  image_generation_test: "Image Generation Test",
};

export const BottomBar = () => {
  const { stdout } = useStdout();
  const { provider } = useProvider();
  const { optionValues } = useOptions();
  const { mode } = useMode();
  const { isFocused } = useFocus();
  const screen = useScreen();

  const modeDisplay =
    screen === "chat" || screen === "mode_runner"
      ? (MODE_LABELS[mode] ?? mode)
      : "Menu";
  const cols = stdout.columns || 120;

  const truncate = (value: string, width: number): string => {
    if (width <= 0) {
      return "";
    }
    if (value.length > width) {
      return width > 3 ? `${value.slice(0, width - 3)}...` : value.slice(0, width);
    }
    return value;
  };

  const modeWidth = Math.max(28, Math.floor(cols * 0.30));
  const hintWidth = Math.max(32, Math.floor(cols * 0.34));
  const optionsWidth = Math.max(
    20,
    cols - modeWidth - hintWidth - 6, // separators + spaces
  );

  const optionTokens = (provider.options || []).map((option) => {
    const currentValue = optionValues[option.id] ?? option.default;
    if (option.type === "boolean") {
      return `(${option.shortcutKey.toUpperCase()}) ${option.name}: ${currentValue ? "On" : "Off"}`;
    }
    const selectedOption = option.options.find((opt) => opt.id === currentValue);
    const label = selectedOption?.label || String(currentValue);
    return `(${option.shortcutKey.toUpperCase()}) ${option.name}: ${label}`;
  });

  const modeSegment = truncate(`Mode: ${modeDisplay}`, modeWidth);
  const optionsSegment = truncate(optionTokens.join("  "), optionsWidth);
  const hintText =
    screen === "mode_runner"
      ? "R: Run again | Up/Down: Scroll | PgUp/PgDn: Page"
      : screen === "chat"
        ? (isFocused
            ? "Enter: Send message | Esc: Settings"
            : "Enter: Focus input | Esc: Menu")
        : "Enter: Select | Esc: Back";
  const hintSegment = truncate(hintText, hintWidth);

  return (
    <Box width="100%">
      <Box width={modeWidth}>
        <Text color="blueBright" wrap="truncate-end">
          {modeSegment}
        </Text>
      </Box>
      <Text color="gray"> | </Text>
      <Box width={optionsWidth}>
        <Text color="cyanBright" wrap="truncate-end">
          {optionsSegment}
        </Text>
      </Box>
      <Text color="gray"> | </Text>
      <Box width={hintWidth}>
        <Text color="greenBright" wrap="truncate-end">
          {hintSegment}
        </Text>
      </Box>
    </Box>
  );
};
