import { Box, Text, useStdout } from "ink";
import { useRuntime } from "./runtime_context.js";
import { useProvider } from "./provider_context.js";
import { useScreen } from "./screen_context.js";
import { useFocus } from "./focus_context.js";

type Segment = { text: string; color: string; bold?: boolean };

export const Statusbar = () => {
  const { stdout } = useStdout();
  const { runtime } = useRuntime();
  const { provider } = useProvider();
  const screen = useScreen();
  const { isFocused } = useFocus();

  const cols = stdout.columns || 120;
  const isRuntimeActive = screen === "runtime_selector";
  const isProviderActive = screen === "provider_selector";
  const isToolsActive = screen === "tool_selector" || screen === "tool_runner";

  const bg = "#B62AD9";
  const sep = " \u2502 ";

  const parts: Segment[] = [
    { text: " \u25A0 LLM Analytics", color: "white", bold: true },
    { text: sep, color: "white" },
    { text: isFocused ? "Esc: Settings" : "Esc: Menu", color: "white" },
    { text: sep, color: "white" },
    {
      text: `R: ${runtime.name()}`,
      color: isRuntimeActive ? "yellowBright" : "white",
    },
    { text: sep, color: "white" },
    {
      text: `P: ${provider.name}`,
      color: isProviderActive ? "yellowBright" : "white",
    },
    { text: sep, color: "white" },
    {
      text: "T: Tools",
      color: isToolsActive ? "yellowBright" : "white",
    },
  ];

  // Truncate the last segment if total exceeds terminal width
  const totalWidth = parts.reduce((sum, p) => sum + p.text.length, 0);
  if (totalWidth > cols) {
    const last = parts[parts.length - 1]!;
    const excess = totalWidth - cols;
    const available = last.text.length - excess;
    last.text =
      available > 3
        ? last.text.slice(0, available - 1) + "\u2026"
        : available > 0
          ? last.text.slice(0, available)
          : "";
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
