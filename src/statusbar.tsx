import { Box, Text, useStdout } from "ink";
import { useRuntime } from "./runtime_context.js";
import { useProvider } from "./provider_context.js";
import { useScreen } from "./screen_context.js";
import { useFocus } from "./focus_context.js";

export const Statusbar = () => {
  const { stdout } = useStdout();
  const { runtime } = useRuntime();
  const { provider } = useProvider();
  const screen = useScreen();
  const { isFocused } = useFocus();

  const isRuntimeActive = screen === "runtime_selector";
  const isProviderActive = screen === "provider_selector";
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

  const separatorWidth = 3;
  const titleWidth = 18;
  const menuWidth = 14;
  const runtimeWidth = 24;
  const providerMinWidth = 20;
  const fixedWidth = titleWidth + menuWidth + runtimeWidth + separatorWidth * 3;
  const providerWidth = Math.max(providerMinWidth, cols - fixedWidth);

  const brandSegment = truncate("LLM Analytics Apps", titleWidth);
  const menuSegment = truncate(
    isFocused ? "(Esc) Settings" : "(Esc) Menu",
    menuWidth,
  );
  const runtimeSegment = truncate(`(R) Runtime: ${runtime.name()}`, runtimeWidth);
  const providerSegment = truncate(`(P) Provider: ${provider.name}`, providerWidth);

  return (
    <Box width="100%">
      <Box width={titleWidth}>
        <Text bold color="cyan" wrap="truncate-end">
          {brandSegment}
        </Text>
      </Box>
      <Text color="gray"> | </Text>
      <Box width={menuWidth}>
        <Text wrap="truncate-end">{menuSegment}</Text>
      </Box>
      <Text color="gray"> | </Text>
      <Box width={runtimeWidth}>
        {isRuntimeActive ? (
          <Text color="yellow" wrap="truncate-end">
            {runtimeSegment}
          </Text>
        ) : (
          <Text dimColor={isFocused} wrap="truncate-end">
            {runtimeSegment}
          </Text>
        )}
      </Box>
      <Text color="gray"> | </Text>
      <Box width={providerWidth}>
        {isProviderActive ? (
          <Text color="green" wrap="truncate-end">
            {providerSegment}
          </Text>
        ) : (
          <Text dimColor={isFocused} wrap="truncate-end">
            {providerSegment}
          </Text>
        )}
      </Box>
    </Box>
  );
};
