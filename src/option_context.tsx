import {
  createContext,
  useContext,
  useState,
  useEffect,
  type ReactNode,
} from "react";
import { useRuntime } from "./runtime_context.js";
import { useProvider, signalOptionChange } from "./provider_context.js";

type OptionContextType = {
  optionValues: Record<string, string | boolean>;
  setOption: (optionId: string, value: string | boolean) => Promise<void>;
  optionChangeCounter: number;
};

const OptionContext = createContext<OptionContextType | null>(null);

export const useOptions = () => {
  const context = useContext(OptionContext);
  if (!context) {
    throw new Error("useOptions must be used within OptionProvider");
  }
  return context;
};

export const OptionProvider = ({ children }: { children: ReactNode }) => {
  const { runtime } = useRuntime();
  const { provider } = useProvider();
  const [optionValues, setOptionValues] = useState<
    Record<string, string | boolean>
  >({});
  const [optionChangeCounter, setOptionChangeCounter] = useState(0);

  // Initialize option values from provider defaults
  useEffect(() => {
    if (provider.options) {
      setOptionValues((prev) => {
        const next: Record<string, string | boolean> = {};
        for (const option of provider.options || []) {
          // Preserve existing value across provider metadata refreshes.
          next[option.id] =
            prev[option.id] !== undefined ? prev[option.id]! : option.default;
        }

        // Keep runtime-side option state in sync with what the UI shows
        // when switching providers.
        void Promise.all(
          (provider.options || []).map((option) =>
            runtime
              .setProviderOption(provider.id, option.id, next[option.id]!)
              .catch((err) =>
                console.error(
                  `[Options] Failed to sync option ${option.id} for provider ${provider.id}:`,
                  err,
                ),
              ),
          ),
        );

        return next;
      });
    }
  }, [provider, runtime]);

  const setOption = async (optionId: string, value: string | boolean) => {
    // Update runtime
    await runtime.setProviderOption(provider.id, optionId, value);

    // Update local state
    setOptionValues((prev) => ({ ...prev, [optionId]: value }));

    // Increment counter to signal change (Chat can listen to this)
    setOptionChangeCounter((prev) => prev + 1);

    // Signal provider to refetch (to get updated input_modes)
    signalOptionChange();
  };

  return (
    <OptionContext.Provider
      value={{ optionValues, setOption, optionChangeCounter }}
    >
      {children}
    </OptionContext.Provider>
  );
};
