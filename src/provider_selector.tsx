import { Box, Text } from "ink";
import SelectInput from "ink-select-input";
import { useProvider } from "./provider_context.js";
import { useNavigateScreen } from "./screen_context.js";

const Indicator = ({ isSelected = false }: { isSelected?: boolean }) => (
  <Box marginRight={1}>
    <Text color={isSelected ? "greenBright" : "gray"}>
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

export const ProviderSelector = () => {
  const { availableProviders, setProvider } = useProvider();
  const navigate = useNavigateScreen();

  if (availableProviders.length === 0) {
    return (
      <Box padding={1} flexDirection="column">
        <Box marginBottom={1} marginLeft={1}>
          <Text bold color="greenBright">
            Select Provider
          </Text>
        </Box>
        <Box borderStyle="round" borderColor="green" paddingX={1}>
          <Text color="red">Please select a runtime first</Text>
        </Box>
      </Box>
    );
  }

  const items = availableProviders.map((provider) => ({
    label: provider.name,
    value: provider.id,
  }));

  const handleSelect = (item: { value: string }) => {
    const selectedProvider = availableProviders.find(
      (p) => p.id === item.value,
    );
    if (selectedProvider) {
      setProvider(selectedProvider);
    }
    navigate("mode_selector");
  };

  return (
    <Box padding={1} flexDirection="column">
      <Box marginBottom={1} marginLeft={1}>
        <Text bold color="greenBright">
          Select Provider
        </Text>
      </Box>
      <Box
        borderStyle="round"
        borderColor="green"
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
