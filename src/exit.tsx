import { useEffect } from "react";
import { useApp } from "ink";

export function Exit() {
  const app = useApp();
  useEffect(() => {
    app.exit();
  }, []);
  return null;
}
