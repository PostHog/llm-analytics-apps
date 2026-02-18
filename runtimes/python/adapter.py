#!/usr/bin/env python3
"""
Unix socket server for Python runtime adapter.
Handles provider discovery and chat requests.
"""

import os
import sys
import socket
import json
import signal
import subprocess
from pathlib import Path
from posthog import Posthog

# Add providers to path
sys.path.insert(0, str(Path(__file__).parent))

from providers import discover_providers

SOCKET_PATH = "/tmp/llm-analytics-python.sock"
PYTHON_RUNTIME_ROOT = Path(__file__).parent
PYTHON_TOOLS_ROOT = PYTHON_RUNTIME_ROOT / "tools"
TOOL_TIMEOUT_SECONDS = 60


class RuntimeAdapter:
    def __init__(self):
        # Environment should be inherited from parent process (Node)
        # Initialize PostHog client
        api_key = os.getenv("POSTHOG_API_KEY")
        if not api_key:
            raise ValueError("POSTHOG_API_KEY not found in environment")

        self.posthog_client = Posthog(
            project_api_key=api_key,
            host=os.getenv("POSTHOG_HOST", "https://app.posthog.com"),
        )

        # Discover providers
        self.providers = {}
        for provider in discover_providers(self.posthog_client):
            name = provider.get_name()
            self.providers[name.lower()] = provider

        print(f"Loaded providers: {list(self.providers.keys())}", file=sys.stderr)
        self.tools = [
            {
                "id": "python_tool_call_selected_provider",
                "name": "Tool Call Smoke Test (Selected Provider)",
                "description": "Runs a weather tool-call test through the active provider.",
            },
            {
                "id": "python_message_selected_provider",
                "name": "Message Smoke Test (Selected Provider)",
                "description": "Runs a simple message test through the active provider.",
            },
            {
                "id": "python_trace_generator",
                "name": "Trace Generator",
                "description": "Runs trace generator in non-interactive mode.",
                "command": sys.executable,
                "args": ["trace_generator.py", "--quick"],
                "cwd": str(PYTHON_TOOLS_ROOT / "trace-generator"),
            },
            {
                "id": "python_screenshot_demo",
                "name": "Screenshot Demo",
                "description": "Runs screenshot demo in non-interactive mode.",
                "command": sys.executable,
                "args": ["screenshot_demo.py", "--tools"],
                "cwd": str(PYTHON_TOOLS_ROOT / "screenshot-demo"),
            },
        ]

    def handle_message(self, message):
        """Handle incoming JSON message"""
        try:
            data = json.loads(message)
            action = data.get("action")

            if action == "get_providers":
                return self.get_providers()
            elif action == "get_provider_options":
                return self.get_provider_options(data.get("provider"))
            elif action == "set_provider_option":
                return self.set_provider_option(
                    data.get("provider"), data.get("option_id"), data.get("value")
                )
            elif action == "chat":
                return self.chat(data.get("provider"), data.get("messages", []))
            elif action == "run_mode_test":
                return self.run_mode_test(data.get("provider"), data.get("mode"))
            elif action == "list_tools":
                return self.list_tools()
            elif action == "run_tool":
                return self.run_tool(data.get("tool_id"), data.get("provider"))
            else:
                return {"error": f"Unknown action: {action}"}

        except Exception as e:
            return {"error": str(e)}

    def get_providers(self):
        """Return list of available providers"""
        providers = [
            {
                "id": name,
                "name": provider.get_name(),
                "options": provider.get_options(),
                "input_modes": provider.get_input_modes(),
            }
            for name, provider in self.providers.items()
        ]
        return {"providers": providers}

    def get_provider_options(self, provider_name):
        """Get options for a specific provider"""
        if not provider_name:
            return {"error": "Provider name required"}

        provider = self.providers.get(provider_name.lower())
        if not provider:
            return {"error": f"Provider not found: {provider_name}"}

        return {"options": provider.get_options()}

    def set_provider_option(self, provider_name, option_id, value):
        """Set an option value for a provider"""
        if not provider_name:
            return {"error": "Provider name required"}

        provider = self.providers.get(provider_name.lower())
        if not provider:
            return {"error": f"Provider not found: {provider_name}"}

        if not option_id:
            return {"error": "Option ID required"}

        try:
            provider.set_option(option_id, value)
            return {"success": True}
        except Exception as e:
            return {"error": f"Failed to set option: {str(e)}"}

    def chat(self, provider_name, messages):
        """Forward chat request to provider"""
        if not provider_name:
            return {"error": "Provider name required"}

        provider = self.providers.get(provider_name.lower())
        if not provider:
            return {"error": f"Provider not found: {provider_name}"}

        try:
            message = provider.chat(messages)
            return {"message": message}
        except Exception as e:
            return {"error": f"Chat failed: {str(e)}"}

    def run_mode_test(self, provider_name, mode):
        if not provider_name:
            return {"error": "Provider name required"}

        provider = self.providers.get(provider_name.lower())
        if not provider:
            return {"error": f"Provider not found: {provider_name}"}

        try:
            if mode == "tool_call_test":
                messages = [{
                    "role": "user",
                    "content": [{"type": "text", "text": "What is the weather in Montreal, Canada?"}]
                }]
                return {"message": provider.chat(messages)}

            if mode == "message_test":
                messages = [{
                    "role": "user",
                    "content": [{"type": "text", "text": "Hi, how are you today?"}]
                }]
                return {"message": provider.chat(messages)}

            if mode == "image_test":
                return {"message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Python runtime image test is not implemented yet."}]
                }}

            if mode == "embeddings_test":
                return {"message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Python runtime embeddings test is not implemented yet."}]
                }}

            if mode == "structured_output_test":
                messages = [{
                    "role": "user",
                    "content": [{"type": "text", "text": "Create a profile for a 25-year-old software developer who loves hiking and photography."}]
                }]
                return {"message": provider.chat(messages)}

            if mode == "transcription_test":
                return {"message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Python runtime transcription test is not implemented yet."}]
                }}

            if mode == "image_generation_test":
                return {"message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Python runtime image generation test is not implemented yet."}]
                }}

            return {"message": {
                "role": "assistant",
                "content": [{"type": "text", "text": f"Unknown mode: {mode}"}]
            }}
        except Exception as e:
            return {"error": f"Mode test failed: {str(e)}"}

    def list_tools(self):
        return {
            "tools": [
                {
                    "id": tool["id"],
                    "name": tool["name"],
                    "description": tool.get("description"),
                }
                for tool in self.tools
            ]
        }

    def run_tool(self, tool_id, provider_name=None):
        if not tool_id:
            return {"error": "tool_id is required"}

        tool = next((candidate for candidate in self.tools if candidate["id"] == tool_id), None)
        if tool is None:
            return {"error": f"Unknown tool: {tool_id}"}

        if tool_id in {"python_tool_call_selected_provider", "python_message_selected_provider"}:
            if not provider_name:
                return {"error": "provider is required for this runtime tool"}

            mode = "tool_call_test" if tool_id == "python_tool_call_selected_provider" else "message_test"
            mode_result = self.run_mode_test(provider_name, mode)
            if "error" in mode_result:
                return mode_result

            message = mode_result.get("message", {})
            text_blocks = [
                block.get("text", "")
                for block in message.get("content", [])
                if block.get("type") == "text"
            ]
            output = "\n".join(text_blocks).strip() or "No output."
            title = "Tool Call Smoke Test" if mode == "tool_call_test" else "Message Smoke Test"

            return {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Tool: {title}\nProvider: {provider_name}\n\n{output}",
                        }
                    ],
                }
            }

        try:
            result = subprocess.run(
                [tool["command"], *tool["args"]],
                cwd=tool["cwd"],
                capture_output=True,
                text=True,
                env=os.environ.copy(),
                timeout=TOOL_TIMEOUT_SECONDS,
                check=False,
            )
            timed_out = False
            exit_code = result.returncode
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
        except subprocess.TimeoutExpired as e:
            timed_out = True
            exit_code = "timeout"
            stdout = (e.stdout or "").strip()
            stderr = (e.stderr or "").strip()
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}

        output = "\n".join(
            [
                f"Tool: {tool['name']}",
                f"Exit code: {exit_code}{' (timed out)' if timed_out else ''}",
                "",
                f"STDOUT:\n{stdout}" if stdout else "STDOUT: (empty)",
                "",
                f"STDERR:\n{stderr}" if stderr else "STDERR: (empty)",
            ]
        )
        if timed_out:
            output += f"\n\nExecution timed out after {TOOL_TIMEOUT_SECONDS}s."

        return {
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": output}],
            }
        }

    def run(self):
        """Start Unix socket server"""
        # Remove old socket if it exists
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)

        # Create Unix socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(SOCKET_PATH)
        sock.listen(1)

        print(f"Listening on {SOCKET_PATH}", file=sys.stderr)

        # Handle shutdown gracefully
        def shutdown(signum, frame):
            print("Shutting down...", file=sys.stderr)
            sock.close()
            if os.path.exists(SOCKET_PATH):
                os.remove(SOCKET_PATH)
            sys.exit(0)

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)

        try:
            while True:
                conn, _ = sock.accept()
                try:
                    # Read message (up to 1MB)
                    data = conn.recv(1024 * 1024).decode("utf-8")
                    if not data:
                        continue

                    # Handle message
                    response = self.handle_message(data)

                    # Send response
                    conn.sendall(json.dumps(response).encode("utf-8"))
                finally:
                    conn.close()

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
        finally:
            sock.close()
            if os.path.exists(SOCKET_PATH):
                os.remove(SOCKET_PATH)


if __name__ == "__main__":
    adapter = RuntimeAdapter()
    adapter.run()
