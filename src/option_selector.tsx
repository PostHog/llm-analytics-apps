import { Box, Text } from "ink";
import SelectInput from "ink-select-input";
import { useNavigateScreen, useCurrentOption } from "./screen_context.js";
import { useOptions } from "./option_context.js";

const Indicator = ({ isSelected = false }: { isSelected?: boolean }) => (
  <Box marginRight={1}>
    <Text color={isSelected ? "cyanBright" : "gray"}>
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
    <Box padding={1} flexDirection="column">
      <Box marginBottom={1} marginLeft={1}>
        <Text bold color="cyanBright">
          {option.name}
        </Text>
      </Box>
      <Box
        borderStyle="round"
        borderColor="cyan"
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
