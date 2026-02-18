import { Box, Text } from "ink";
import SelectInput from "ink-select-input";
import { useNavigateScreen, useCurrentOption } from "./screen_context.js";
import { useOptions } from "./option_context.js";

export const OptionSelector = () => {
  const navigate = useNavigateScreen();
  const option = useCurrentOption();
  const { setOption } = useOptions();

  if (!option) {
    return (
      <Box padding={1} borderStyle="round" borderColor="cyan">
        <Text color="red">No option selected</Text>
      </Box>
    );
  }

  const items = option.options.map((opt) => ({
    label: opt.label,
    value: opt.id,
  }));

  const handleSelect = async (item: { value: string }) => {
    await setOption(option.id, item.value);
    navigate("chat");
  };

  return (
    <Box
      padding={1}
      borderStyle="round"
      borderColor="cyan"
      flexDirection="column"
    >
      <SelectInput items={items} onSelect={handleSelect} />
    </Box>
  );
};
