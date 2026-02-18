import path from "path";
import fs from "fs/promises";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { Box, Text } from "ink";
import RuntimeAdapter from "./runtime_adapters/utils/base.js";

type RuntimeContextType = {
  runtime: RuntimeAdapter;
  setRuntime: (runtime: RuntimeAdapter) => Promise<void>;
  availableRuntimes: RuntimeAdapter[];
};

const RuntimeContext = createContext<RuntimeContextType | null>(null);

export const useRuntime = (): NonNullable<RuntimeContextType> => {
  const context = useContext(RuntimeContext);
  if (!context?.runtime) {
    throw new Error("useRuntime must be used within RuntimeProvider");
  }
  return context;
};

async function getRuntimes(): Promise<RuntimeAdapter[]> {
  const runtimeDir = path.join(import.meta.dirname, "runtime_adapters");
  const entries = await fs.readdir(runtimeDir, { withFileTypes: true });
  const runtimePaths = entries
    .filter((entry) => entry.isFile() && path.extname(entry.name) === ".js")
    .map((entry) => entry.name);

  const runtimes = await Promise.all(
    runtimePaths.map(async (file) => {
      const fullPath = path.join(runtimeDir, file);
      const module = await import(fullPath);
      const RuntimeClass = module.default;
      if (!(RuntimeClass.prototype instanceof RuntimeAdapter)) {
        throw new Error(
          `Runtime ${file} is not a valid runtime as it does not extend RuntimeAdapter`,
        );
      }

      return new RuntimeClass() as RuntimeAdapter;
    }),
  );
  return runtimes.sort((a, b) => (a.name() < b.name() ? -1 : 1));
}

export const RuntimeProvider = ({ children }: { children: ReactNode }) => {
  const [runtime, setRuntime] = useState<RuntimeAdapter | null>(null);
  const [availableRuntimes, setAvailableRuntimes] = useState<RuntimeAdapter[]>(
    [],
  );
  const [startupError, setStartupError] = useState<string | null>(null);

  const pickInitialRuntime = (runtimes: RuntimeAdapter[]): RuntimeAdapter | null => {
    const nodeRuntime = runtimes.find((rt) => rt.id() === "node");
    if (nodeRuntime) {
      return nodeRuntime;
    }

    const pythonRuntime = runtimes.find((rt) => rt.id() === "python");
    if (pythonRuntime) {
      return pythonRuntime;
    }

    return runtimes[0] || null;
  };

  useEffect(() => {
    getRuntimes()
      .then(async (runtimes) => {
        setAvailableRuntimes(runtimes);
        const firstRuntime = pickInitialRuntime(runtimes);
        if (firstRuntime) {
          try {
            await firstRuntime.start();
            setRuntime(firstRuntime);
            setStartupError(null);
          } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            setStartupError(`Failed to start runtime "${firstRuntime.name()}": ${message}`);
          }
        }
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : String(err);
        setStartupError(`Failed to discover runtimes: ${message}`);
      });
  }, []);

  const setRuntimeWithLifecycle = async (newRuntime: RuntimeAdapter) => {
    const oldRuntime = runtime;
    if (!oldRuntime || oldRuntime.id() === newRuntime.id()) {
      return;
    }

    try {
      // Temporarily clear runtime so children that call runtime methods unmount.
      setRuntime(null);
      await oldRuntime.stop();

      await newRuntime.start();
      setRuntime(newRuntime);
      setStartupError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setStartupError(`Failed to start runtime "${newRuntime.name()}": ${message}`);

      try {
        await oldRuntime.start();
        setRuntime(oldRuntime);
      } catch {
        // no-op: keep the error state visible
      }

      throw err;
    }
  };

  if (!runtime) {
    if (startupError) {
      return (
        <Box flexDirection="column" padding={1}>
          <Text color="red">Runtime startup failed</Text>
          <Text>{startupError}</Text>
        </Box>
      );
    }

    return (
      <Box padding={1}>
        <Text dimColor>Starting runtime...</Text>
      </Box>
    );
  }

  return (
    <RuntimeContext.Provider
      value={{
        runtime,
        setRuntime: setRuntimeWithLifecycle,
        availableRuntimes,
      }}
    >
      {children}
    </RuntimeContext.Provider>
  );
};
