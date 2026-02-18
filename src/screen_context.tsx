import { createContext, useContext, useState } from "react";
import type { ProviderOption } from "./types.js";

export type Screen =
  | "mode_selector"
  | "chat"
  | "exit"
  | "runtime_selector"
  | "provider_selector"
  | "option_selector"
  | "mode_runner";

const ScreenContext = createContext<{
  screen: Screen;
  navigate: (screen: Screen) => void;
  currentOption: Extract<ProviderOption, { type: "enum" }> | null;
  setCurrentOption: (
    option: Extract<ProviderOption, { type: "enum" }> | null,
  ) => void;
}>({
  screen: "mode_selector",
  navigate: () => {},
  currentOption: null,
  setCurrentOption: () => {},
});

export function ScreenProvider({ children }: { children: React.ReactNode }) {
  const [screen, setScreen] = useState<Screen>("mode_selector");
  const [currentOption, setCurrentOption] = useState<Extract<
    ProviderOption,
    { type: "enum" }
  > | null>(null);

  return (
    <ScreenContext.Provider
      value={{ screen, navigate: setScreen, currentOption, setCurrentOption }}
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
