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
  structured_output_test: "Structured Output",
  transcription_test: "Transcription Test",
  image_generation_test: "Image Generation",
};

type Segment = { text: string; color: string; bold?: boolean };

export const BottomBar = () => {
  const { stdout } = useStdout();
  const { provider } = useProvider();
  const { optionValues } = useOptions();
  const { mode } = useMode();
  const { isFocused } = useFocus();
  const screen = useScreen();

  const cols = stdout.columns || 120;
  const modeDisplay =
    screen === "chat" || screen === "mode_runner"
      ? (MODE_LABELS[mode] ?? mode)
      : "Menu";

  const optionTokens = (provider.options || []).map((option) => {
    const currentValue = optionValues[option.id] ?? option.default;
    if (option.type === "boolean") {
      return `(${option.shortcutKey.toUpperCase()}) ${option.name}: ${currentValue ? "On" : "Off"}`;
    }
    const selectedOption = option.options.find(
      (opt) => opt.id === currentValue,
    );
    const label = selectedOption?.label || String(currentValue);
    return `(${option.shortcutKey.toUpperCase()}) ${option.name}: ${label}`;
  });

  const hintText =
    screen === "mode_runner"
      ? "R: Rerun \u2502 \u2191\u2193: Scroll \u2502 PgUp/PgDn: Page"
      : screen === "chat"
        ? isFocused
          ? "Enter: Send \u2502 Esc: Settings"
          : "Enter: Focus \u2502 Esc: Menu"
        : "Enter: Select \u2502 Esc: Back";

  const bg = "gray";
  const sep = " \u2502 ";

  const parts: Segment[] = [
    { text: ` ${modeDisplay}`, color: "cyanBright", bold: true },
  ];

  if (optionTokens.length > 0) {
    parts.push({ text: sep, color: "white" });
    parts.push({ text: optionTokens.join("  "), color: "yellowBright" });
  }

  parts.push({ text: sep, color: "white" });
  parts.push({ text: hintText, color: "white" });

  // Truncate last content segment if total exceeds terminal width
  const totalWidth = parts.reduce((sum, p) => sum + p.text.length, 0);
  if (totalWidth > cols) {
    for (let i = parts.length - 1; i >= 0; i--) {
      if (parts[i]!.text !== sep) {
        const excess = totalWidth - cols;
        const available = parts[i]!.text.length - excess;
        parts[i]!.text =
          available > 3
            ? parts[i]!.text.slice(0, available - 1) + "\u2026"
            : available > 0
              ? parts[i]!.text.slice(0, available)
              : "";
        break;
      }
    }
  }

  const renderedWidth = parts.reduce((sum, p) => sum + p.text.length, 0);
  const padWidth = Math.max(0, cols - renderedWidth);

  return (
    <Box width={cols}>
      {parts.map((part, i) => (
        <Text
          key={i}
          backgroundColor={bg}
          color={part.color}
          bold={part.bold === true}
        >
          {part.text}
        </Text>
      ))}
      {padWidth > 0 && <Text backgroundColor={bg}>{" ".repeat(padWidth)}</Text>}
    </Box>
  );
};
