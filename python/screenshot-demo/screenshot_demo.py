#!/usr/bin/env python3
"""
Screenshot Demo for PostHog LLM Analytics

Demonstrates how screenshot/image data sent with AI generations appears in PostHog's
LLM Analytics traces and generations view.

This is useful for products that send screenshots of users' computers along with
messages to their AI, where responses include tool calls, responses, and thinking traces.
"""

import os
import sys
import base64
import uuid
import platform
import subprocess
import random
from typing import Optional
from dotenv import load_dotenv

# Enable multimodal capture in PostHog SDK (preserves base64 images instead of redacting)
os.environ["_INTERNAL_LLMA_MULTIMODAL"] = "true"

from posthog import Posthog

# Add parent directory to path for provider imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from posthog.ai.anthropic import Anthropic
from posthog.ai.openai import OpenAI

# Load environment variables from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))


class ScreenshotDemo:
    """Demo tool for sending screenshots with LLM requests to PostHog"""

    def __init__(self):
        self.debug_mode = os.getenv('DEBUG') == '1'

        # Validate environment
        if not self._validate_environment():
            print("Environment validation failed. Please check your .env file.")
            sys.exit(1)

        # Generate session ID for grouping traces
        self.ai_session_id = str(uuid.uuid4())

        # Initialize PostHog client
        self.posthog = Posthog(
            os.getenv("POSTHOG_API_KEY"),
            host=os.getenv("POSTHOG_HOST", "https://app.posthog.com"),
            super_properties={"$ai_session_id": self.ai_session_id}
        )

        self.distinct_id = os.getenv("POSTHOG_DISTINCT_ID", "screenshot-demo-user")

        # Initialize AI clients with PostHog integration
        self.anthropic_client = None
        self.openai_client = None

        if os.getenv("ANTHROPIC_API_KEY"):
            self.anthropic_client = Anthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                posthog_client=self.posthog
            )

        if os.getenv("OPENAI_API_KEY"):
            self.openai_client = OpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                posthog_client=self.posthog
            )

        print("PostHog client initialized successfully")
        print(f"AI Session ID: {self.ai_session_id}")

    def _validate_environment(self) -> bool:
        """Validate required environment variables"""
        api_key = os.getenv("POSTHOG_API_KEY")
        if not api_key or len(api_key) < 10:
            print("POSTHOG_API_KEY is missing or invalid")
            return False

        # Need at least one AI provider
        if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("OPENAI_API_KEY"):
            print("At least one of ANTHROPIC_API_KEY or OPENAI_API_KEY is required")
            return False

        return True

    def clear_screen(self):
        """Clear the terminal screen"""
        if not self.debug_mode:
            os.system('cls' if platform.system() == 'Windows' else 'clear')

    def capture_screenshot(self) -> Optional[str]:
        """Capture a screenshot and return as base64 string"""
        temp_path = "/tmp/screenshot_demo.png"

        try:
            system = platform.system()

            if system == "Darwin":  # macOS
                subprocess.run(
                    ["screencapture", "-x", temp_path],
                    check=True,
                    capture_output=True
                )
            elif system == "Linux":
                # Try various screenshot tools
                tools = [
                    ["gnome-screenshot", "-f", temp_path],
                    ["scrot", temp_path],
                    ["import", "-window", "root", temp_path]
                ]
                captured = False
                for tool in tools:
                    try:
                        subprocess.run(tool, check=True, capture_output=True)
                        captured = True
                        break
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        continue

                if not captured:
                    print("No screenshot tool found. Install gnome-screenshot, scrot, or imagemagick.")
                    return None
            elif system == "Windows":
                # Windows screenshot requires pillow or similar
                print("Windows screenshot capture not implemented. Please provide an image file.")
                return None
            else:
                print(f"Unsupported platform: {system}")
                return None

            # Read and encode the screenshot
            with open(temp_path, "rb") as f:
                image_data = f.read()

            # Clean up temp file
            os.remove(temp_path)

            return base64.b64encode(image_data).decode("utf-8")

        except subprocess.CalledProcessError as e:
            print(f"Screenshot capture failed: {e}")
            return None
        except Exception as e:
            print(f"Error capturing screenshot: {e}")
            return None

    def load_image_file(self, file_path: str) -> Optional[str]:
        """Load an image file and return as base64 string"""
        try:
            with open(file_path, "rb") as f:
                image_data = f.read()
            return base64.b64encode(image_data).decode("utf-8")
        except FileNotFoundError:
            print(f"File not found: {file_path}")
            return None
        except Exception as e:
            print(f"Error loading image: {e}")
            return None

    def get_sample_screenshot(self) -> tuple[str, str]:
        """Load a random sample screenshot from the samples folder.

        Returns:
            Tuple of (base64_image, image_name) or (None, None) if no images found.
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))
        samples_dir = os.path.join(script_dir, "samples")

        # Get list of PNG files in samples directory
        if os.path.exists(samples_dir):
            sample_files = [f for f in os.listdir(samples_dir) if f.endswith('.png')]
            if sample_files:
                selected = random.choice(sample_files)
                sample_path = os.path.join(samples_dir, selected)
                image_data = self.load_image_file(sample_path)
                if image_data:
                    return image_data, selected

        # Fallback to single sample-screenshot.png
        sample_path = os.path.join(script_dir, "sample-screenshot.png")
        if os.path.exists(sample_path):
            image_data = self.load_image_file(sample_path)
            if image_data:
                return image_data, "sample-screenshot.png"

        print("No sample images found.")
        print(f"Please add PNG files to: {samples_dir}")
        return None, None

    def send_with_anthropic(self, query: str, base64_image: str, with_tools: bool = False) -> str:
        """Send a screenshot with query to Anthropic Claude"""
        if not self.anthropic_client:
            return "Anthropic client not available (missing API key)"

        # Build message with image
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": query},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64_image
                        }
                    }
                ]
            }
        ]

        # Define tools if requested (simulating computer-use style tool calls)
        tools = None
        if with_tools:
            tools = [
                {
                    "name": "click_element",
                    "description": "Click on a UI element at the specified coordinates",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number", "description": "X coordinate"},
                            "y": {"type": "number", "description": "Y coordinate"},
                            "element_description": {"type": "string", "description": "Description of the element to click"}
                        },
                        "required": ["x", "y"]
                    }
                },
                {
                    "name": "type_text",
                    "description": "Type text at the current cursor position",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "Text to type"}
                        },
                        "required": ["text"]
                    }
                },
                {
                    "name": "scroll",
                    "description": "Scroll the current view",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                            "amount": {"type": "number", "description": "Amount to scroll in pixels"}
                        },
                        "required": ["direction"]
                    }
                }
            ]

        request_params = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "posthog_distinct_id": self.distinct_id,
            "messages": messages
        }

        if tools:
            request_params["tools"] = tools

        try:
            response = self.anthropic_client.messages.create(**request_params)

            # Extract response text
            result_parts = []
            for block in response.content:
                if hasattr(block, 'text'):
                    result_parts.append(block.text)
                elif hasattr(block, 'type') and block.type == 'tool_use':
                    result_parts.append(f"[Tool Call: {block.name}({block.input})]")

            return "\n".join(result_parts) if result_parts else "No response"

        except Exception as e:
            return f"Error: {str(e)}"

    def send_with_openai(self, query: str, base64_image: str, with_tools: bool = False) -> str:
        """Send a screenshot with query to OpenAI GPT-4 Vision"""
        if not self.openai_client:
            return "OpenAI client not available (missing API key)"

        # Build message with image
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": query},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]

        # Define tools if requested
        tools = None
        if with_tools:
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "click_element",
                        "description": "Click on a UI element at the specified coordinates",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number", "description": "X coordinate"},
                                "y": {"type": "number", "description": "Y coordinate"},
                                "element_description": {"type": "string", "description": "Description of the element"}
                            },
                            "required": ["x", "y"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "type_text",
                        "description": "Type text at the current cursor position",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string", "description": "Text to type"}
                            },
                            "required": ["text"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "scroll",
                        "description": "Scroll the current view",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                                "amount": {"type": "number", "description": "Amount to scroll"}
                            },
                            "required": ["direction"]
                        }
                    }
                }
            ]

        request_params = {
            "model": "gpt-4o",
            "max_tokens": 1024,
            "posthog_distinct_id": self.distinct_id,
            "messages": messages
        }

        if tools:
            request_params["tools"] = tools

        try:
            response = self.openai_client.chat.completions.create(**request_params)

            choice = response.choices[0]
            result_parts = []

            if choice.message.content:
                result_parts.append(choice.message.content)

            if choice.message.tool_calls:
                for tool_call in choice.message.tool_calls:
                    result_parts.append(f"[Tool Call: {tool_call.function.name}({tool_call.function.arguments})]")

            return "\n".join(result_parts) if result_parts else "No response"

        except Exception as e:
            return f"Error: {str(e)}"

    def run_demo(self, image_source: str = "sample", with_tools: bool = True):
        """Run the screenshot demo"""
        print("\n" + "=" * 60)
        print("Screenshot Demo for PostHog LLM Analytics")
        print("=" * 60)

        # Get the image
        base64_image = None

        image_name = None
        if image_source == "capture":
            print("\nCapturing screenshot...")
            base64_image = self.capture_screenshot()
            image_name = "captured-screenshot.png"
        elif image_source == "sample":
            print("\nSelecting random sample image...")
            base64_image, image_name = self.get_sample_screenshot()
        elif os.path.isfile(image_source):
            print(f"\nLoading image from: {image_source}")
            base64_image = self.load_image_file(image_source)
            image_name = os.path.basename(image_source)
        else:
            print(f"\nInvalid image source: {image_source}")
            return

        if not base64_image:
            print("Failed to get image data")
            return

        image_size_kb = len(base64_image) / 1024
        print(f"Selected: {image_name}")
        print(f"Image size: {image_size_kb:.1f} KB (base64)")

        # Sample queries that simulate computer-use style interactions
        queries = [
            "What do you see in this screenshot? Describe the UI elements visible.",
            "Can you help me click on the search button in this screenshot?",
            "I want to navigate to the settings menu. What should I click?",
        ]

        query = queries[0]
        if with_tools:
            query = "Look at this screenshot and help me interact with it. What elements do you see and what actions would you recommend?"

        print(f"\nQuery: {query}")
        print(f"With tools: {with_tools}")

        # Send to available providers
        results = {}

        if self.anthropic_client:
            print("\n--- Sending to Anthropic Claude ---")
            results["anthropic"] = self.send_with_anthropic(query, base64_image, with_tools)
            print(f"Response: {results['anthropic'][:500]}..." if len(results.get('anthropic', '')) > 500 else f"Response: {results.get('anthropic', 'N/A')}")

        if self.openai_client:
            print("\n--- Sending to OpenAI GPT-4o ---")
            results["openai"] = self.send_with_openai(query, base64_image, with_tools)
            print(f"Response: {results['openai'][:500]}..." if len(results.get('openai', '')) > 500 else f"Response: {results.get('openai', 'N/A')}")

        # Flush PostHog events
        self.posthog.flush()

        print("\n" + "=" * 60)
        print("Events sent to PostHog!")
        print(f"Session ID: {self.ai_session_id}")
        print("=" * 60)
        print("\nCheck PostHog LLM Analytics to see how the screenshot data appears:")
        print("1. Go to your PostHog project")
        print("2. Navigate to LLM Analytics / Generations")
        print("3. Look for the $ai_input field - it will contain the image data")
        print("4. The traces view will show the full request/response with image")
        print("=" * 60)

        return results

    def interactive_menu(self):
        """Run interactive menu"""
        while True:
            self.clear_screen()
            print("\n" + "=" * 60)
            print("Screenshot Demo for PostHog LLM Analytics")
            print("=" * 60)
            print(f"\nSession ID: {self.ai_session_id}")
            print("\nThis demo shows how screenshot/image data appears in PostHog's")
            print("LLM Analytics - useful for computer-use products that send")
            print("screenshots with AI requests.\n")

            print("Available providers:")
            if self.anthropic_client:
                print("  - Anthropic Claude")
            if self.openai_client:
                print("  - OpenAI GPT-4o")

            print("\nOptions:")
            print("  1. Send sample image (quick demo)")
            print("  2. Send sample image with tool calls")
            print("  3. Capture screenshot and send")
            print("  4. Load image file and send")
            print("  5. Custom query with sample image")
            print("  6. Exit")

            try:
                choice = input("\nSelect option (1-6): ").strip()

                if choice == "1":
                    self.run_demo("sample", with_tools=False)
                    input("\nPress Enter to continue...")
                elif choice == "2":
                    self.run_demo("sample", with_tools=True)
                    input("\nPress Enter to continue...")
                elif choice == "3":
                    self.run_demo("capture", with_tools=True)
                    input("\nPress Enter to continue...")
                elif choice == "4":
                    file_path = input("Enter image file path: ").strip()
                    if file_path:
                        self.run_demo(file_path, with_tools=True)
                    input("\nPress Enter to continue...")
                elif choice == "5":
                    self.custom_query_demo()
                    input("\nPress Enter to continue...")
                elif choice == "6":
                    print("\nGoodbye!")
                    break
                else:
                    print("Invalid choice")
                    input("\nPress Enter to continue...")

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break

    def custom_query_demo(self):
        """Send a custom query with sample image"""
        print("\n--- Custom Query Demo ---")
        query = input("Enter your query: ").strip()
        if not query:
            print("No query provided")
            return

        with_tools_input = input("Include tools? (y/n, default: y): ").strip().lower()
        with_tools = with_tools_input != 'n'

        base64_image, image_name = self.get_sample_screenshot()
        if not base64_image:
            print("No sample image available")
            return
        print(f"Using image: {image_name}")

        if self.anthropic_client:
            print("\n--- Anthropic Response ---")
            response = self.send_with_anthropic(query, base64_image, with_tools)
            print(response)

        if self.openai_client:
            print("\n--- OpenAI Response ---")
            response = self.send_with_openai(query, base64_image, with_tools)
            print(response)

        self.posthog.flush()
        print(f"\nEvents sent! Session ID: {self.ai_session_id}")


def main():
    """Main entry point"""
    demo = ScreenshotDemo()

    # Check for command line arguments
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--quick":
            demo.run_demo("sample", with_tools=False)
        elif arg == "--tools":
            demo.run_demo("sample", with_tools=True)
        elif arg == "--capture":
            demo.run_demo("capture", with_tools=True)
        elif os.path.isfile(arg):
            demo.run_demo(arg, with_tools=True)
        else:
            print(f"Usage: {sys.argv[0]} [--quick|--tools|--capture|<image_file>]")
            print("  --quick   : Quick demo with sample image, no tools")
            print("  --tools   : Demo with sample image and tool calls")
            print("  --capture : Capture screenshot and send")
            print("  <file>    : Load specific image file")
            print("  (no args) : Interactive menu")
    else:
        demo.interactive_menu()


if __name__ == "__main__":
    main()
