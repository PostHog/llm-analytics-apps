import { createContext, useContext, useState, type ReactNode } from "react";

export type AppMode =
  | "chat"
  | "tool_call_test"
  | "message_test"
  | "image_test"
  | "embeddings_test"
  | "structured_output_test"
  | "transcription_test"
  | "image_generation_test";

type ModeContextType = {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
};

const ModeContext = createContext<ModeContextType | null>(null);

export const ModeProvider = ({ children }: { children: ReactNode }) => {
  const [mode, setMode] = useState<AppMode>("chat");

  return (
    <ModeContext.Provider value={{ mode, setMode }}>
      {children}
    </ModeContext.Provider>
  );
};

export const useMode = (): ModeContextType => {
  const context = useContext(ModeContext);
  if (!context) {
    throw new Error("useMode must be used within ModeProvider");
  }
  return context;
};
