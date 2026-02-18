import { Box, Text } from "ink";
import SelectInput from "ink-select-input";
import { useRuntime } from "./runtime_context.js";
import { useNavigateScreen } from "./screen_context.js";

const Indicator = ({ isSelected = false }: { isSelected?: boolean }) => (
  <Box marginRight={1}>
    <Text color={isSelected ? "yellowBright" : "gray"}>
      {isSelected ? "\u25B8" : " "}
    </Text>
  </Box>
);

const Item = ({
  isSelected = false,
  label = "",
}: {
  isSelected?: boolean;
  label?: string;
}) => (
  <Text color="white" bold={isSelected} dimColor={!isSelected}>
    {label}
  </Text>
);

export const RuntimeSelector = () => {
  const { availableRuntimes, setRuntime } = useRuntime();
  const navigate = useNavigateScreen();

  const items = availableRuntimes.map((runtime) => ({
    label: runtime.name(),
    value: runtime,
  }));

  const handleSelect = async (item: {
    value: (typeof availableRuntimes)[number];
  }) => {
    try {
      await setRuntime(item.value);
      navigate("mode_selector");
    } catch {
      // Runtime context surfaces the error state.
    }
  };

  return (
    <Box padding={1} flexDirection="column">
      <Box marginBottom={1} marginLeft={1}>
        <Text bold color="yellowBright">
          Select Runtime
        </Text>
      </Box>
      <Box
        borderStyle="round"
        borderColor="yellow"
        paddingX={1}
        flexDirection="column"
      >
        <SelectInput
          items={items}
          onSelect={handleSelect}
          indicatorComponent={Indicator}
          itemComponent={Item}
        />
      </Box>
    </Box>
  );
};
