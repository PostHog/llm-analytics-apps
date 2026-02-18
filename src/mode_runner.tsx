import { Box, Text, useInput, useStdout } from "ink";
import { useEffect, useState } from "react";
import { useProvider } from "./provider_context.js";
import { useRuntime } from "./runtime_context.js";
import { useMode } from "./mode_context.js";

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

function wrapLine(line: string, width: number): string[] {
  if (width <= 0) {
    return [line];
  }
  if (line.length === 0) {
    return [""];
  }
  const wrapped: string[] = [];
  let start = 0;
  while (start < line.length) {
    wrapped.push(line.slice(start, start + width));
    start += width;
  }
  return wrapped;
}

export const ModeRunner = () => {
  const { runtime } = useRuntime();
  const { provider } = useProvider();
  const { mode } = useMode();
  const { stdout } = useStdout();
  const [isRunning, setIsRunning] = useState(true);
  const [output, setOutput] = useState("");
  const [scrollOffset, setScrollOffset] = useState(0);

  const run = async () => {
    setIsRunning(true);
    setScrollOffset(0);
    try {
      const message = await runtime.runModeTest(provider.id, mode);
      const text = message.content
        .filter((block) => block.type === "text")
        .map((block) => block.text)
        .join("\n");
      setOutput(text || "No output received.");
    } catch (err) {
      setOutput(`Error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsRunning(false);
    }
  };

  useEffect(() => {
    void run();
  }, [provider.id, mode, runtime]);

  const outputWidth = Math.max(20, (stdout.columns || 80) - 4);
  const outputLines = output
    .split("\n")
    .flatMap((line) => wrapLine(line, outputWidth));
  const chromeLines = 8;
  const visibleLineCount = Math.max(4, (stdout.rows || 24) - chromeLines);
  const maxOffset = Math.max(0, outputLines.length - visibleLineCount);
  const startLine = Math.min(scrollOffset, maxOffset);
  const endLine = startLine + visibleLineCount;
  const visibleLines = outputLines.slice(startLine, endLine);

  useEffect(() => {
    setScrollOffset((prev) => Math.min(prev, maxOffset));
  }, [maxOffset]);

  useInput((input, key) => {
    if (input.toLowerCase() === "r" && !isRunning) {
      void run();
      return;
    }

    if (key.upArrow || input.toLowerCase() === "k") {
      setScrollOffset((prev) => Math.max(0, prev - 1));
      return;
    }

    if (key.downArrow || input.toLowerCase() === "j") {
      setScrollOffset((prev) => Math.min(maxOffset, prev + 1));
      return;
    }

    if (key.pageUp) {
      setScrollOffset((prev) => Math.max(0, prev - visibleLineCount));
      return;
    }

    if (key.pageDown) {
      setScrollOffset((prev) => Math.min(maxOffset, prev + visibleLineCount));
    }
  });

  return (
    <Box flexDirection="column" padding={1} flexGrow={1}>
      <Text bold color="#B62AD9">
        {MODE_LABELS[mode] || mode}
      </Text>
      <Text dimColor>
        {`${provider.name} \u00B7 ${isRunning ? "Running\u2026" : "Complete"}`}
      </Text>
      <Box marginTop={1}>
        <Text>{visibleLines.join("\n")}</Text>
      </Box>
      {outputLines.length > visibleLineCount && (
        <Box marginTop={1}>
          <Text dimColor>
            {`Lines ${startLine + 1}\u2013${Math.min(outputLines.length, endLine)} of ${outputLines.length} \u00B7 \u2191\u2193/j/k: Scroll \u00B7 PgUp/PgDn: Page`}
          </Text>
        </Box>
      )}
    </Box>
  );
};
