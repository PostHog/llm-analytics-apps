import { Box, Text } from "ink";

interface AttachmentStatusbarProps {
  fileCount: number;
  isFocused: boolean;
}

export const AttachmentStatusbar = ({
  fileCount,
  isFocused,
}: AttachmentStatusbarProps) => {
  if (fileCount === 0) {
    return null;
  }

  const fileText =
    fileCount === 1 ? "1 file attached" : `${fileCount} files attached`;
  const clearHint = isFocused ? "(ESC+C to clear)" : "(C to clear)";

  return (
    <Box marginBottom={1}>
      <Text color="yellowBright" bold>
        [{fileText}]
      </Text>
      <Text dimColor> {clearHint}</Text>
    </Box>
  );
};
