import { Box, useStdout } from "ink";
import { useLayoutEffect, useState, type ReactNode } from "react";

export const Fullscreen = ({ children }: { children: ReactNode }) => {
  const { stdout } = useStdout();
  const [size, setSize] = useState({
    width: stdout.columns,
    height: stdout.rows,
  });

  useLayoutEffect(() => {
    // Enter alternate screen buffer
    stdout.write("\x1b[?1049h");

    const handleResize = () => {
      setSize({
        width: stdout.columns,
        height: stdout.rows,
      });
    };

    stdout.on("resize", handleResize);
    handleResize();

    return () => {
      // Exit alternate screen buffer
      stdout.write("\x1b[?1049l");
      stdout.off("resize", handleResize);
    };
  }, [stdout]);

  return (
    <Box width={size.width} height={size.height} flexDirection="column">
      {children}
    </Box>
  );
};
