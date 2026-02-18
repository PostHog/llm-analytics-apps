export type Message = {
  role: "user" | "assistant" | "system";
  content: ContentBlock[];
};

export type ContentBlock =
  | {
      type: "text";
      text: string;
    }
  | {
      type: "file";
      path: string;
      mimeType: string;
    }
  | {
      type: "audio";
      path: string;
      transcript: string;
    }
  | {
      type: "image";
      path: string;
      alt?: string;
    };

export function isTextBlock(
  block: ContentBlock,
): block is Extract<ContentBlock, { type: "text" }> {
  return block.type === "text";
}

export function isFileBlock(
  block: ContentBlock,
): block is Extract<ContentBlock, { type: "file" }> {
  return block.type === "file";
}

export function isAudioBlock(
  block: ContentBlock,
): block is Extract<ContentBlock, { type: "audio" }> {
  return block.type === "audio";
}

export function isImageBlock(
  block: ContentBlock,
): block is Extract<ContentBlock, { type: "image" }> {
  return block.type === "image";
}

export type ProviderOption =
  | {
      id: string;
      name: string;
      shortcutKey: string;
      type: "boolean";
      default: boolean;
    }
  | {
      id: string;
      name: string;
      shortcutKey: string;
      type: "enum";
      default: string;
      options: Array<{ id: string; label: string }>;
    };

export type InputMode = "text" | "audio" | "image" | "video" | "file";

export type Provider = {
  id: string;
  name: string;
  options?: ProviderOption[];
  input_modes: InputMode[];
};

export type RuntimeTool = {
  id: string;
  name: string;
  description?: string;
};
