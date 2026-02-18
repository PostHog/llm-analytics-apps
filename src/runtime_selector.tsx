import { Box } from "ink";
import SelectInput from "ink-select-input";
import { useRuntime } from "./runtime_context.js";
import { useNavigateScreen } from "./screen_context.js";

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
    <Box
      padding={1}
      borderStyle="round"
      borderColor="yellow"
      flexDirection="column"
    >
      <SelectInput items={items} onSelect={handleSelect} />
    </Box>
  );
};
