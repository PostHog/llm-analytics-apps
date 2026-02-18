import {
  createContext,
  useContext,
  useState,
  useEffect,
  type ReactNode,
} from "react";
import { Box, Text } from "ink";
import type { Provider } from "./types.js";
import { useRuntime } from "./runtime_context.js";

let optionChangeSignal = 0;

export const signalOptionChange = () => {
  optionChangeSignal++;
};

type ProviderContextType = {
  provider: Provider;
  setProvider: (provider: Provider) => void;
  availableProviders: Provider[];
};

const ProviderContext = createContext<ProviderContextType | null>(null);

export const useProvider = (): NonNullable<ProviderContextType> => {
  const context = useContext(ProviderContext);
  if (!context) {
    throw new Error("useProvider must be used within ProviderProvider");
  }
  return context;
};

export const ProviderProvider = ({ children }: { children: ReactNode }) => {
  const { runtime } = useRuntime();
  const [provider, setProvider] = useState<Provider | null>(null);
  const [availableProviders, setAvailableProviders] = useState<Provider[]>([]);
  const [signal, setSignal] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Poll for option changes
  useEffect(() => {
    const interval = setInterval(() => {
      if (optionChangeSignal !== signal) {
        setSignal(optionChangeSignal);
      }
    }, 100);
    return () => clearInterval(interval);
  }, [signal]);

  useEffect(() => {
    let cancelled = false;

    runtime
      .getProviders()
      .then((providers) => {
        if (cancelled) {
          return;
        }

        if (providers.length === 0) {
          setAvailableProviders([]);
          setProvider(null);
          setLoadError(`No providers found for runtime ${runtime.name()}`);
          return;
        }

        setAvailableProviders(providers);
        setLoadError(null);

        setProvider((currentProvider) => {
          if (currentProvider) {
            const matchingProvider = providers.find(
              (p) => p.id === currentProvider.id,
            );
            if (matchingProvider) {
              return matchingProvider;
            }
          }

          if (runtime.id() === "node") {
            const preferredNodeProvider = providers.find(
              (p) => p.id === "openai_chat",
            );
            if (preferredNodeProvider) {
              return preferredNodeProvider;
            }
          }

          return providers[0] || null;
        });
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        console.error(`[Provider] Failed to load providers: ${error}`);
        setAvailableProviders([]);
        setProvider(null);
        setLoadError(
          `Failed to load providers for runtime ${runtime.name()}: ${error instanceof Error ? error.message : String(error)}`,
        );
      });

    return () => {
      cancelled = true;
    };
  }, [runtime, signal]);

  if (!provider) {
    return (
      <Box padding={1} flexDirection="column">
        {loadError ? (
          <>
            <Text color="red">Provider loading failed</Text>
            <Text>{loadError}</Text>
          </>
        ) : (
          <Text dimColor>Loading providers...</Text>
        )}
      </Box>
    );
  }

  return (
    <ProviderContext.Provider
      value={{ provider, setProvider, availableProviders }}
    >
      {children}
    </ProviderContext.Provider>
  );
};
