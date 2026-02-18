import {
  useScreen,
  useNavigateScreen,
  useSetCurrentOption,
} from "./screen_context.js";
import { Box, render, useApp, useInput } from "ink";
import { useEffect } from "react";
import { Fullscreen } from "./fullscreen.js";
import { Statusbar } from "./statusbar.js";
import { BottomBar } from "./bottombar.js";
import { ModeSelector } from "./mode_selector.js";
import { Chat } from "./chat.js";
import { Exit } from "./exit.js";
import { ScreenProvider } from "./screen_context.js";
import { RuntimeProvider } from "./runtime_context.js";
import { ProviderProvider } from "./provider_context.js";
import { OptionProvider } from "./option_context.js";
import { FocusProvider, useFocus } from "./focus_context.js";
import { RuntimeSelector } from "./runtime_selector.js";
import { ProviderSelector } from "./provider_selector.js";
import { OptionSelector } from "./option_selector.js";
import { useProvider } from "./provider_context.js";
import { useOptions } from "./option_context.js";
import { ModeProvider } from "./mode_context.js";
import { ModeRunner } from "./mode_runner.js";
import { config } from "dotenv";
import fs from "fs";
import path from "path";

// Load environment variables
const cwdEnvPath = path.join(process.cwd(), ".env");
if (fs.existsSync(cwdEnvPath)) {
  config({ path: cwdEnvPath });
}

// Validate required environment variables
const requiredEnvVars = ["POSTHOG_API_KEY", "OPENAI_API_KEY"];
const missingVars = requiredEnvVars.filter((varName) => !process.env[varName]);

if (missingVars.length > 0) {
  console.error("Error: Missing required environment variables:");
  missingVars.forEach((varName) => {
    console.error(`  - ${varName}`);
  });
  console.error(
    "\nPlease create a .env file in the repository root with these variables.",
  );
  console.error("See .env.example for reference.");
  process.exit(1);
}

const App = () => {
  useProcessExitSignals();

  return (
    <Fullscreen>
      <FocusProvider>
        <RuntimeProvider>
          <ProviderProvider>
            <OptionProvider>
              <ModeProvider>
                <ScreenProvider>
                  <Statusbar />
                  <Box flexGrow={1}>
                    <Screens />
                  </Box>
                  <BottomBar />
                </ScreenProvider>
              </ModeProvider>
            </OptionProvider>
          </ProviderProvider>
        </RuntimeProvider>
      </FocusProvider>
    </Fullscreen>
  );
};

function useProcessExitSignals() {
  const app = useApp();

  useEffect(() => {
    const shutdown = () => {
      app.exit();
      // Fallback in case event-loop handles remain alive.
      setImmediate(() => process.exit(0));
    };

    process.on("SIGINT", shutdown);
    process.on("SIGTERM", shutdown);

    return () => {
      process.off("SIGINT", shutdown);
      process.off("SIGTERM", shutdown);
    };
  }, [app]);
}

function Screens() {
  const screen = useScreen();
  const navigate = useNavigateScreen();
  const { isFocused, setFocused } = useFocus();
  const { provider } = useProvider();
  const { optionValues, setOption } = useOptions();
  const setCurrentOption = useSetCurrentOption();

  useInput((input, key) => {
    if (key.escape) {
      if (isFocused) {
        setFocused(false);
      } else {
        navigate("mode_selector");
      }
    } else if (input === "r" || input === "R") {
      if (!isFocused) {
        navigate("runtime_selector");
      }
    } else if (input === "p" || input === "P") {
      if (!isFocused) {
        navigate("provider_selector");
      }
    } else if (!isFocused && provider.options && screen !== "option_selector") {
      const matchedOption = provider.options.find(
        (option) =>
          input.toLowerCase() === option.shortcutKey.toLowerCase(),
      );

      if (matchedOption) {
        if (matchedOption.type === "boolean") {
          const currentValue = (optionValues[matchedOption.id] ??
            matchedOption.default) as boolean;
          void setOption(matchedOption.id, !currentValue);
        } else if (matchedOption.type === "enum") {
          setCurrentOption(matchedOption);
          navigate("option_selector");
        }
      }
    }
  });

  switch (screen) {
    case "mode_selector":
      return <ModeSelector />;
    case "chat":
      return <Chat />;
    case "exit":
      return <Exit />;
    case "runtime_selector":
      return <RuntimeSelector />;
    case "provider_selector":
      return <ProviderSelector />;
    case "option_selector":
      return <OptionSelector />;
    case "mode_runner":
      return <ModeRunner />;
  }
}

render(<App />);
