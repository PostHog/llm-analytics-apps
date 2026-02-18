import { Box, Text } from "ink";
import SelectInput from "ink-select-input";
import { useEffect, useMemo, useState } from "react";
import { useRuntime } from "./runtime_context.js";
import {
  useNavigateScreen,
  useSetCurrentToolId,
} from "./screen_context.js";
import type { RuntimeTool } from "./types.js";

type Item = {
  label: string;
  value: string;
};

const Indicator = ({ isSelected = false }: { isSelected?: boolean }) => (
  <Box marginRight={1}>
    <Text color={isSelected ? "#B62AD9" : "gray"}>
      {isSelected ? "\u25B8" : " "}
    </Text>
  </Box>
);

export function ToolSelector() {
  const navigate = useNavigateScreen();
  const setCurrentToolId = useSetCurrentToolId();
  const { runtime } = useRuntime();
  const [tools, setTools] = useState<RuntimeTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    runtime
      .getTools()
      .then((loadedTools) => {
        setTools(loadedTools);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [runtime]);

  const items = useMemo<Item[]>(() => {
    const toolItems = tools.map((tool) => ({
      label: tool.description ? `${tool.name} - ${tool.description}` : tool.name,
      value: tool.id,
    }));
    toolItems.push({
      label: "Back",
      value: "__back__",
    });
    return toolItems;
  }, [tools]);

  if (loading) {
    return (
      <Box padding={1}>
        <Text dimColor>Loading tools...</Text>
      </Box>
    );
  }

  if (error) {
    return (
      <Box flexDirection="column" padding={1}>
        <Text color="red">Failed to load tools</Text>
        <Text>{error}</Text>
      </Box>
    );
  }

  if (tools.length === 0) {
    return (
      <Box flexDirection="column" padding={1}>
        <Text>No runtime tools available for {runtime.name()}.</Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" padding={1}>
      <Box marginBottom={1}>
        <Text bold>Runtime tools</Text>
      </Box>
      <SelectInput
        items={items}
        indicatorComponent={Indicator}
        onSelect={(item) => {
          if (item.value === "__back__") {
            setCurrentToolId(null);
            navigate("mode_selector");
          } else {
            setCurrentToolId(item.value);
            navigate("tool_runner");
          }
        }}
      />
    </Box>
  );
}
