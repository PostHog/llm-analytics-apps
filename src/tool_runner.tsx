import { Box, Text, useInput, useStdout } from "ink";
import { useEffect, useMemo, useState } from "react";
import { useRuntime } from "./runtime_context.js";
import { useCurrentToolId } from "./screen_context.js";
import { useProvider } from "./provider_context.js";

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

export function ToolRunner() {
  const { runtime } = useRuntime();
  const { provider } = useProvider();
  const toolId = useCurrentToolId();
  const { stdout } = useStdout();
  const [toolName, setToolName] = useState<string>(toolId || "Unknown tool");
  const [isRunning, setIsRunning] = useState(false);
  const [output, setOutput] = useState("");
  const [scrollOffset, setScrollOffset] = useState(0);

  const run = async () => {
    if (!toolId) {
      setOutput("No tool selected.");
      return;
    }

    setIsRunning(true);
    setScrollOffset(0);
    try {
      const message = await runtime.runTool(toolId, provider.id);
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
    if (!toolId) {
      return;
    }
    runtime
      .getTools()
      .then((tools) => {
        const match = tools.find((tool) => tool.id === toolId);
        setToolName(match?.name || toolId);
      })
      .catch(() => {
        setToolName(toolId);
      });
  }, [runtime, toolId, provider.id]);

  useEffect(() => {
    void run();
  }, [runtime, toolId]);

  const outputWidth = Math.max(20, (stdout.columns || 80) - 4);
  const outputLines = useMemo(
    () => output.split("\n").flatMap((line) => wrapLine(line, outputWidth)),
    [output, outputWidth],
  );
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
        Runtime Tool
      </Text>
      <Text dimColor>{`${toolName} · ${isRunning ? "Running…" : "Complete"}`}</Text>
      <Box marginTop={1}>
        <Text>{visibleLines.join("\n")}</Text>
      </Box>
      {outputLines.length > visibleLineCount && (
        <Box marginTop={1}>
          <Text dimColor>
            {`Lines ${startLine + 1}–${Math.min(outputLines.length, endLine)} of ${outputLines.length} · ↑↓/j/k: Scroll · PgUp/PgDn: Page`}
          </Text>
        </Box>
      )}
    </Box>
  );
}
