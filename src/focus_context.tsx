import { createContext, useContext, useState, type ReactNode } from "react";

type FocusContextType = {
  isFocused: boolean;
  setFocused: (focused: boolean) => void;
};

const FocusContext = createContext<FocusContextType | null>(null);

export const useFocus = () => {
  const context = useContext(FocusContext);
  if (!context) {
    throw new Error("useFocus must be used within FocusProvider");
  }
  return context;
};

export const FocusProvider = ({ children }: { children: ReactNode }) => {
  const [isFocused, setFocused] = useState(false);

  return (
    <FocusContext.Provider value={{ isFocused, setFocused }}>
      {children}
    </FocusContext.Provider>
  );
};
