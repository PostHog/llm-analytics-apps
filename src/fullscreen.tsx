import { Box, useStdout } from "ink";
import { useLayoutEffect, useState, type ReactNode } from "react";

export const Fullscreen = ({ children }: { children: ReactNode }) => {
  const { stdout } = useStdout();
  const useAlternateScreen = process.env["LLM_ANALYTICS_NO_ALT_SCREEN"] !== "1";
  const [size, setSize] = useState({
    width: stdout.columns,
    height: stdout.rows,
  });

  useLayoutEffect(() => {
    if (useAlternateScreen) {
      // Enter alternate screen buffer.
      stdout.write("\x1b[?1049h");
    }

    const handleResize = () => {
      setSize({
        width: stdout.columns,
        height: stdout.rows,
      });
    };

    stdout.on("resize", handleResize);
    handleResize();

    return () => {
      if (useAlternateScreen) {
        // Exit alternate screen buffer.
        stdout.write("\x1b[?1049l");
      }
      stdout.off("resize", handleResize);
    };
  }, [stdout, useAlternateScreen]);

  return (
    <Box width={size.width} height={size.height} flexDirection="column">
      {children}
    </Box>
  );
};
