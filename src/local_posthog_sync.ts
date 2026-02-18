import fs from "fs/promises";

function getCookieHeader(headers: Headers): string {
  const headersWithGetSetCookie = headers as Headers & {
    getSetCookie?: () => string[];
  };

  if (typeof headersWithGetSetCookie.getSetCookie === "function") {
    const values = headersWithGetSetCookie.getSetCookie();
    if (values.length > 0) {
      return values.map((cookie) => cookie.split(";")[0]).join("; ");
    }
  }

  const raw = headers.get("set-cookie");
  if (!raw) {
    return "";
  }
  return raw
    .split(/,(?=[^;,=\s]+=[^;,=\s]+)/g)
    .map((cookie) => cookie.split(";")[0])
    .join("; ");
}

function updateEnvContent(content: string, key: string, value: string): string {
  const line = `${key}=${value}`;
  if (new RegExp(`^${key}=`, "m").test(content)) {
    return content.replace(new RegExp(`^${key}=.*$`, "m"), line);
  }
  return content.endsWith("\n") ? `${content}${line}\n` : `${content}\n${line}\n`;
}

export async function syncLocalPostHogApiKey(envPath: string): Promise<void> {
  const host = process.env["POSTHOG_HOST"] || "https://app.posthog.com";
  if (host !== "http://localhost:8010") {
    return;
  }

  const email = process.env["POSTHOG_LOCAL_EMAIL"] || "test@posthog.com";
  const password = process.env["POSTHOG_LOCAL_PASSWORD"] || "12345678";

  try {
    const loginResponse = await fetch(`${host}/api/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    if (loginResponse.status !== 200) {
      console.warn(
        `[prepare] Could not log in to ${host} (status ${loginResponse.status}). Skipping local key sync.`,
      );
      return;
    }

    const cookieHeader = getCookieHeader(loginResponse.headers);
    if (!cookieHeader) {
      console.warn(
        "[prepare] Login succeeded but no session cookie was returned. Skipping local key sync.",
      );
      return;
    }

    const projectResponse = await fetch(`${host}/api/projects/@current`, {
      headers: { Cookie: cookieHeader },
    });

    if (!projectResponse.ok) {
      console.warn(
        `[prepare] Failed to fetch current project (status ${projectResponse.status}). Skipping local key sync.`,
      );
      return;
    }

    const projectData = (await projectResponse.json()) as { api_token?: string };
    const localApiKey = projectData.api_token;
    if (!localApiKey) {
      console.warn(
        "[prepare] Could not parse local PostHog api_token. Skipping local key sync.",
      );
      return;
    }

    if (process.env["POSTHOG_API_KEY"] === localApiKey) {
      return;
    }

    process.env["POSTHOG_API_KEY"] = localApiKey;

    let currentEnv = "";
    try {
      currentEnv = await fs.readFile(envPath, "utf8");
    } catch {
      // file may not exist yet
    }

    const updated = updateEnvContent(currentEnv, "POSTHOG_API_KEY", localApiKey);
    await fs.writeFile(envPath, updated, "utf8");
    console.log("[prepare] Synced POSTHOG_API_KEY from local PostHog instance.");
  } catch (error) {
    console.warn(
      `[prepare] Local key sync failed: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}
