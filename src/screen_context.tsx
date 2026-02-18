import { createContext, useContext, useState } from "react";
import type { ProviderOption } from "./types.js";

export type Screen =
  | "mode_selector"
  | "chat"
  | "exit"
  | "runtime_selector"
  | "provider_selector"
  | "option_selector"
  | "mode_runner"
  | "tool_selector"
  | "tool_runner";

const ScreenContext = createContext<{
  screen: Screen;
  navigate: (screen: Screen) => void;
  currentOption: Extract<ProviderOption, { type: "enum" }> | null;
  setCurrentOption: (
    option: Extract<ProviderOption, { type: "enum" }> | null,
  ) => void;
  currentToolId: string | null;
  setCurrentToolId: (toolId: string | null) => void;
}>({
  screen: "mode_selector",
  navigate: () => {},
  currentOption: null,
  setCurrentOption: () => {},
  currentToolId: null,
  setCurrentToolId: () => {},
});

export function ScreenProvider({ children }: { children: React.ReactNode }) {
  const [screen, setScreen] = useState<Screen>("mode_selector");
  const [currentOption, setCurrentOption] = useState<Extract<
    ProviderOption,
    { type: "enum" }
  > | null>(null);
  const [currentToolId, setCurrentToolId] = useState<string | null>(null);

  return (
    <ScreenContext.Provider
      value={{
        screen,
        navigate: setScreen,
        currentOption,
        setCurrentOption,
        currentToolId,
        setCurrentToolId,
      }}
    >
      {children}
    </ScreenContext.Provider>
  );
}

export function useScreen() {
  return useContext(ScreenContext).screen;
}

export function useNavigateScreen() {
  return useContext(ScreenContext).navigate;
}

export function useCurrentOption() {
  return useContext(ScreenContext).currentOption;
}

export function useSetCurrentOption() {
  return useContext(ScreenContext).setCurrentOption;
}

export function useCurrentToolId() {
  return useContext(ScreenContext).currentToolId;
}

export function useSetCurrentToolId() {
  return useContext(ScreenContext).setCurrentToolId;
}
