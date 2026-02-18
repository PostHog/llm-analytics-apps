import { useState, useEffect } from "react";
import { Box, Text, useInput, useStdout } from "ink";
import TextInput from "ink-text-input";
import Link from "ink-link";
import { spawn } from "child_process";
import { platform } from "os";
import { useFocus } from "./focus_context.js";
import type { Message, ContentBlock } from "./types.js";
import { isTextBlock, isAudioBlock, isImageBlock } from "./types.js";
import { useRuntime } from "./runtime_context.js";
import { AttachmentStatusbar } from "./attachment_statusbar.js";
import { useProvider } from "./provider_context.js";
import { useOptions } from "./option_context.js";
import { useNavigateScreen, useSetCurrentOption } from "./screen_context.js";
import mime from "mime-types";

// Detect MIME type from file path
function detectMimeType(filePath: string): string {
  const mimeType = mime.lookup(filePath);
  // Return detected type or default to binary
  return mimeType || "application/octet-stream";
}

// Detect file path from drag-and-drop paste (always single-quoted full path)
function detectFilePath(
  text: string,
): { filePath: string; remainingText: string } | null {
  // Match single-quoted path that starts with / (absolute path)
  const match = text.match(/'(\/[^']+)'/);
  if (match && match[1]) {
    const filePath = match[1];

    // Basic validation: path should look like a real file path
    // Must have at least one path separator and shouldn't be just "/"
    if (filePath.length > 1 && filePath.includes("/")) {
      const remainingText = text
        .replace(match[0], " ")
        .replace(/\s+/g, " ")
        .trim();
      return { filePath, remainingText };
    }
  }
  return null;
}

export const Chat = () => {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [attachedFiles, setAttachedFiles] = useState<string[]>([]);
  const [inputKey, setInputKey] = useState(0);
  const { runtime } = useRuntime();
  const { provider } = useProvider();
  const { optionChangeCounter, setOption, optionValues } = useOptions();
  const { isFocused, setFocused } = useFocus();
  const navigate = useNavigateScreen();
  const setCurrentOption = useSetCurrentOption();
  const { stdout } = useStdout();

  useEffect(() => {
    setFocused(true);
    return () => {
      setFocused(false);
    };
  }, [setFocused]);

  // Clear messages when options change
  useEffect(() => {
    if (optionChangeCounter > 0) {
      setMessages([]);
    }
  }, [optionChangeCounter]);

  // Auto-play audio when audio messages arrive
  useEffect(() => {
    const lastMessage = messages[messages.length - 1];
    if (!lastMessage || lastMessage.role !== "assistant") return;

    const audioBlocks = lastMessage.content.filter(isAudioBlock);
    const audioBlock = audioBlocks[0];
    if (!audioBlock) return;

    // Play audio from the shell (not Python!)
    const sys = platform();

    if (sys === "darwin") {
      // macOS
      spawn("afplay", [audioBlock.path]);
    } else if (sys === "linux") {
      // Linux
      spawn("aplay", [audioBlock.path]);
    }
  }, [messages]);

  const handleInputChange = (value: string) => {
    // Check if provider accepts file inputs
    const supportsFiles =
      provider.input_modes.includes("image") ||
      provider.input_modes.includes("audio") ||
      provider.input_modes.includes("video") ||
      provider.input_modes.includes("file");

    if (!supportsFiles) {
      // Just update text, don't detect files
      setInput(value);
      return;
    }

    const result = detectFilePath(value);

    if (result) {
      setAttachedFiles([...attachedFiles, result.filePath]);
      setInput(result.remainingText);
      // Force TextInput remount to reset internal state
      setInputKey((k) => k + 1);
    } else {
      setInput(value);
    }
  };

  useInput((input, key) => {
    if (key.return && !isFocused) {
      setFocused(true);
    }

    if (!isFocused && input.toLowerCase() === "c") {
      setAttachedFiles([]);
    }

    // Handle option shortcuts (only when not focused)
    if (!isFocused && provider.options) {
      for (const option of provider.options) {
        if (input.toLowerCase() === option.shortcutKey.toLowerCase()) {
          if (option.type === "boolean") {
            // Toggle boolean option immediately
            const currentValue = (optionValues[option.id] ??
              option.default) as boolean;
            setOption(option.id, !currentValue);
          } else if (option.type === "enum") {
            // Navigate to option selector
            setCurrentOption(option);
            navigate("option_selector");
          }
          break;
        }
      }
    }
  });

  const handleSubmit = async (value: string) => {
    if (value.trim() || attachedFiles.length > 0) {
      const content: ContentBlock[] = [];

      if (value.trim()) {
        content.push({ type: "text", text: value });
      }

      for (const filePath of attachedFiles) {
        content.push({
          type: "file",
          path: filePath,
          mimeType: detectMimeType(filePath),
        });
      }

      const userMessage: Message = {
        role: "user",
        content,
      };
      const updatedMessages = [...messages, userMessage];
      setMessages(updatedMessages);
      setInput("");
      setAttachedFiles([]);
      const streamingEnabled = Boolean(optionValues["streaming"]);
      const supportsRuntimeStreaming = typeof runtime.chatStream === "function";

      if (streamingEnabled && supportsRuntimeStreaming) {
        const placeholderMessage: Message = {
          role: "assistant",
          content: [{ type: "text", text: "" }],
        };
        setMessages([...updatedMessages, placeholderMessage]);

        const assistantMessage = await runtime.chatStream!(
          provider.id,
          updatedMessages,
          (chunk) => {
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (!last || last.role !== "assistant") {
                return prev;
              }

              const firstBlock = last.content[0];
              if (!firstBlock || firstBlock.type !== "text") {
                return prev;
              }

              const next = [...prev];
              next[next.length - 1] = {
                ...last,
                content: [
                  {
                    ...firstBlock,
                    text: firstBlock.text + chunk,
                  },
                  ...last.content.slice(1),
                ],
              };
              return next;
            });
          },
        );

        setMessages([...updatedMessages, assistantMessage]);
      } else {
        const assistantMessage = await runtime.chat(provider.id, updatedMessages);
        setMessages([...updatedMessages, assistantMessage]);
      }
    }
  };

  const terminalHeight = stdout?.rows || 24;
  const maxVisibleMessages = Math.max(5, Math.floor((terminalHeight - 6) / 3)); // ~3 lines per message
  const visibleMessages = messages.slice(-maxVisibleMessages);

  // Generate input mode hint
  const supportsFiles =
    provider.input_modes.includes("image") ||
    provider.input_modes.includes("audio") ||
    provider.input_modes.includes("video") ||
    provider.input_modes.includes("file");

  const inputModeHint = supportsFiles
    ? "Drag files to attach. Accepts: " + provider.input_modes.join(", ")
    : "Text only";

  return (
    <Box flexDirection="column" height="100%">
      <Box flexDirection="column" flexGrow={1} padding={1} overflow="hidden">
        {messages.length === 0 ? (
          <Box flexDirection="column">
            <Text color="gray">No messages yet. Start typing below...</Text>
            <Text color="gray">{inputModeHint}</Text>
          </Box>
        ) : (
          visibleMessages.map((msg, idx) => {
            return (
              <Box key={idx} marginBottom={1} flexDirection="column">
                <Text bold color={msg.role === "user" ? "green" : "blue"}>
                  {msg.role === "user" ? "You" : "Assistant"}:
                </Text>
                {msg.content.map((block, blockIdx) => {
                  if (isTextBlock(block)) {
                    return <Text key={blockIdx}>{block.text}</Text>;
                  } else if (isAudioBlock(block)) {
                    return (
                      <Box key={blockIdx} flexDirection="column" marginTop={1}>
                        <Text color="cyan" bold>
                          🔊 Audio Response
                        </Text>
                        <Text dimColor>Transcript:</Text>
                        <Text>{block.transcript}</Text>
                        <Box marginTop={1}>
                          <Text dimColor>File: </Text>
                          <Link url={`file://${block.path}`}>{block.path}</Link>
                        </Box>
                      </Box>
                    );
                  } else if (isImageBlock(block)) {
                    return (
                      <Box key={blockIdx} flexDirection="column" marginTop={1}>
                        <Text color="magenta" bold>
                          🖼️ Image
                        </Text>
                        {block.alt && <Text dimColor>{block.alt}</Text>}
                        <Box marginTop={1}>
                          <Text dimColor>File: </Text>
                          <Link url={`file://${block.path}`}>{block.path}</Link>
                        </Box>
                      </Box>
                    );
                  }
                  return null;
                })}
              </Box>
            );
          })
        )}
      </Box>
      {!isFocused && (
        <Box marginBottom={1}>
          <Text color="yellow">Press Return to write</Text>
        </Box>
      )}
      <AttachmentStatusbar
        fileCount={attachedFiles.length}
        isFocused={isFocused}
      />
      <Box marginBottom={1}>
        <Box marginRight={1}>
          <Text>{">"}</Text>
        </Box>
        <TextInput
          key={inputKey}
          value={input}
          onChange={handleInputChange}
          onSubmit={handleSubmit}
          placeholder={isFocused ? "Type your message..." : ""}
          focus={isFocused}
        />
      </Box>
    </Box>
  );
};
