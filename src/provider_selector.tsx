import { Box, Text } from "ink";
import SelectInput from "ink-select-input";
import { useProvider } from "./provider_context.js";
import { useNavigateScreen } from "./screen_context.js";

export const ProviderSelector = () => {
  const { availableProviders, setProvider } = useProvider();
  const navigate = useNavigateScreen();

  if (availableProviders.length === 0) {
    return (
      <Box padding={1} borderStyle="round" borderColor="green">
        <Text color="red">Please select a runtime first</Text>
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
    <Box
      padding={1}
      borderStyle="round"
      borderColor="green"
      flexDirection="column"
    >
      <SelectInput items={items} onSelect={handleSelect} />
    </Box>
  );
};
