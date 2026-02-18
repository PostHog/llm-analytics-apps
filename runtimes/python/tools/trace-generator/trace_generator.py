#!/usr/bin/env python3
"""
Interactive LLM Trace Generator
Creates arbitrarily complex nested trace data for PostHog analytics testing
"""

import os
import sys
import uuid
import json
import time
import platform
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from posthog import Posthog

# Load environment variables from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

class EventGenerator:
    """Generates realistic mock data for different event types"""

    # Sample data for realistic mock generation
    SAMPLE_USER_QUERIES = [
        "What's the weather like in San Francisco?",
        "Can you help me write a Python function to calculate the factorial of a number?",
        "Explain the concept of machine learning in simple terms",
        "What are some good restaurants near Times Square?",
        "How do I invest in the stock market as a beginner?",
        "Tell me about the history of the Internet",
        "What's the best way to learn a new programming language?",
        "Can you summarize the latest news about artificial intelligence?"
    ]

    SAMPLE_AI_RESPONSES = [
        "I'd be happy to help you with that! Let me provide you with some information.",
        "Based on my analysis, here's what I found:",
        "That's a great question! Here's my explanation:",
        "I can help you with that. Let me break this down for you:",
        "Here's a comprehensive answer to your question:",
        "Let me search for the most current information on this topic.",
        "I'll provide you with a detailed response based on my knowledge:",
        "That's an interesting topic! Here's what you need to know:"
    ]

    SAMPLE_DOCUMENTS = [
        {"title": "API Documentation", "content": "Complete guide to using our REST API endpoints"},
        {"title": "User Manual", "content": "Step-by-step instructions for getting started"},
        {"title": "Technical Specifications", "content": "Detailed technical requirements and specifications"},
        {"title": "FAQ", "content": "Frequently asked questions and answers"},
        {"title": "Troubleshooting Guide", "content": "Common issues and their solutions"},
        {"title": "Best Practices", "content": "Recommended approaches and methodologies"}
    ]

    SAMPLE_TOOLS = [
        {"name": "get_weather", "description": "Get current weather for a location"},
        {"name": "search_web", "description": "Search the web for information"},
        {"name": "calculate", "description": "Perform mathematical calculations"},
        {"name": "get_stock_price", "description": "Get current stock price for a symbol"},
        {"name": "send_email", "description": "Send an email to specified recipients"},
        {"name": "schedule_meeting", "description": "Schedule a meeting in the calendar"}
    ]

    @staticmethod
    def generate_trace_id() -> str:
        """Generate a unique trace ID"""
        return str(uuid.uuid4())

    @staticmethod
    def generate_span_id() -> str:
        """Generate a unique span ID"""
        return str(uuid.uuid4())

    @staticmethod
    def get_current_timestamp():
        """Get current timestamp as datetime object for PostHog"""
        return datetime.now(timezone.utc)

    @classmethod
    def generate_trace_event(cls, trace_id: str, span_name: str = "chat_completion") -> Dict[str, Any]:
        """Generate a minimal trace event - app computes aggregates from children"""
        return {
            "event": "$ai_trace",
            "properties": {
                "$ai_trace_id": trace_id,
                "$ai_span_name": span_name,
                "$ai_is_error": False
            },
            "timestamp": cls.get_current_timestamp()
        }

    @classmethod
    def generate_span_event(cls, trace_id: str, span_name: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate a realistic span event"""
        span_id = cls.generate_span_id()

        # Generate different input/output based on span type
        if "retrieval" in span_name.lower() or "search" in span_name.lower():
            input_state = {"query": cls._random_choice(cls.SAMPLE_USER_QUERIES), "limit": 5}
            output_state = {"documents": cls.SAMPLE_DOCUMENTS[:3], "count": 3}
        elif "tool" in span_name.lower():
            tool = cls._random_choice(cls.SAMPLE_TOOLS)
            input_state = {"tool_name": tool["name"], "arguments": {"param": "value"}}
            output_state = {"result": "Tool execution completed successfully", "status": "success"}
        else:
            input_state = {"operation": span_name, "parameters": {"type": "default"}}
            output_state = {"result": "Operation completed", "duration": 0.234}

        properties = {
            "$ai_trace_id": trace_id,
            "$ai_span_id": span_id,
            "$ai_span_name": span_name,
            "$ai_input_state": input_state,
            "$ai_output_state": output_state,
            "$ai_latency": round(0.1 + (time.time() % 2), 3),
            "$ai_is_error": False
        }

        if parent_id:
            properties["$ai_parent_id"] = parent_id

        return {
            "event": "$ai_span",
            "properties": properties,
            "timestamp": cls.get_current_timestamp()
        }

    @classmethod
    def generate_generation_event(cls, trace_id: str, model: str = "gpt-4o-mini",
                                  parent_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate a realistic generation event"""
        span_id = cls.generate_span_id()
        user_input = cls._random_choice(cls.SAMPLE_USER_QUERIES)
        ai_output = cls._random_choice(cls.SAMPLE_AI_RESPONSES)

        properties = {
            "$ai_trace_id": trace_id,
            "$ai_span_id": span_id,
            "$ai_model": model,
            "$ai_provider": "openai" if "gpt" in model else "anthropic",
            "$ai_input": [{"role": "user", "content": user_input}],
            "$ai_input_tokens": str(int(len(user_input.split()) * 1.3)),  # Rough token approximation
            "$ai_output_choices": [{"role": "assistant", "content": ai_output}],
            "$ai_output_tokens": str(int(len(ai_output.split()) * 1.3)),
            "$ai_latency": round(1.0 + (time.time() % 4), 3),
            "$ai_http_status": 200,
            "$ai_base_url": "https://api.openai.com/v1",
            "$ai_request_url": "https://api.openai.com/v1/chat/completions",
            "$ai_is_error": False,
            "$ai_temperature": 0.7,
            "$ai_stream": False,
            "$ai_max_tokens": 500,
            "$ai_span_name": "chat_completion"
        }

        if parent_id:
            properties["$ai_parent_id"] = parent_id

        return {
            "event": "$ai_generation",
            "properties": properties,
            "timestamp": cls.get_current_timestamp()
        }

    @classmethod
    def generate_embedding_event(cls, trace_id: str, model: str = "text-embedding-3-small",
                                 parent_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate a realistic embedding event"""
        span_id = cls.generate_span_id()
        text_input = cls._random_choice(cls.SAMPLE_USER_QUERIES)

        properties = {
            "$ai_trace_id": trace_id,
            "$ai_span_id": span_id,
            "$ai_model": model,
            "$ai_provider": "openai",
            "$ai_input": text_input,
            "$ai_input_tokens": str(int(len(text_input.split()) * 1.3)),
            "$ai_latency": round(0.1 + (time.time() % 1), 3),
            "$ai_http_status": 200,
            "$ai_base_url": "https://api.openai.com/v1",
            "$ai_request_url": "https://api.openai.com/v1/embeddings",
            "$ai_is_error": False,
            "$ai_span_name": "text_embedding"
        }

        if parent_id:
            properties["$ai_parent_id"] = parent_id

        return {
            "event": "$ai_embedding",
            "properties": properties,
            "timestamp": cls.get_current_timestamp()
        }

    @classmethod
    def generate_custom_generation_event(cls, trace_id: str, model: str, purpose: str, name: str,
                                         parent_id: Optional[str] = None, user_input: Optional[str] = None,
                                         assistant_output: Optional[str] = None) -> Dict[str, Any]:
        """Generate a custom generation event with specific purpose or manual text"""
        span_id = cls.generate_span_id()

        # Use manual text if provided, otherwise generate content based on purpose
        if user_input is not None and assistant_output is not None:
            input_content, output_content = user_input, assistant_output
        else:
            input_content, output_content = cls._get_purpose_content(purpose)

        properties = {
            "$ai_trace_id": trace_id,
            "$ai_span_id": span_id,
            "$ai_model": model,
            "$ai_provider": "openai" if "gpt" in model else "anthropic",
            "$ai_input": [{"role": "user", "content": input_content}],
            "$ai_input_tokens": str(int(len(input_content.split()) * 1.3)),
            "$ai_output_choices": [{"role": "assistant", "content": output_content}],
            "$ai_output_tokens": str(int(len(output_content.split()) * 1.3)),
            "$ai_latency": round(1.0 + (time.time() % 4), 3),
            "$ai_http_status": 200,
            "$ai_base_url": "https://api.openai.com/v1",
            "$ai_request_url": "https://api.openai.com/v1/chat/completions",
            "$ai_is_error": False,
            "$ai_temperature": 0.7,
            "$ai_stream": False,
            "$ai_max_tokens": 500,
            "$ai_span_name": name
        }

        if parent_id:
            properties["$ai_parent_id"] = parent_id

        return {
            "event": "$ai_generation",
            "properties": properties,
            "timestamp": cls.get_current_timestamp()
        }

    @classmethod
    def generate_custom_embedding_event(cls, trace_id: str, model: str, name: str,
                                        parent_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate a custom embedding event"""
        span_id = cls.generate_span_id()
        text_input = cls._random_choice(cls.SAMPLE_USER_QUERIES)

        properties = {
            "$ai_trace_id": trace_id,
            "$ai_span_id": span_id,
            "$ai_model": model,
            "$ai_provider": "openai",
            "$ai_input": text_input,
            "$ai_input_tokens": str(int(len(text_input.split()) * 1.3)),
            "$ai_latency": round(0.1 + (time.time() % 1), 3),
            "$ai_http_status": 200,
            "$ai_base_url": "https://api.openai.com/v1",
            "$ai_request_url": "https://api.openai.com/v1/embeddings",
            "$ai_is_error": False,
            "$ai_span_name": name
        }

        if parent_id:
            properties["$ai_parent_id"] = parent_id

        return {
            "event": "$ai_embedding",
            "properties": properties,
            "timestamp": cls.get_current_timestamp()
        }

    @classmethod
    def _get_purpose_content(cls, purpose: str) -> tuple:
        """Get appropriate input/output content based on generation purpose"""
        purpose_templates = {
            "planning": (
                "I need to break down this complex task into manageable steps. Can you help me create a plan?",
                "I'll help you create a structured plan. Let me break this down into clear, actionable steps for you."
            ),
            "tool_call": (
                "I need to get the current weather in San Francisco.",
                "I'll fetch the current weather information for San Francisco using the weather API."
            ),
            "synthesis": (
                "Based on all the information gathered, can you provide a comprehensive summary?",
                "Here's a comprehensive synthesis of all the information: The analysis shows clear patterns and actionable insights."
            ),
            "reasoning": (
                "Let me think through this step by step to understand the implications.",
                "After careful analysis, here's my reasoning: The evidence suggests a clear logical progression that leads to this conclusion."
            ),
            "code_generation": (
                "Can you write a Python function to calculate the factorial of a number?",
                "Here's a Python function that calculates factorial: def factorial(n): return 1 if n <= 1 else n * factorial(n-1)"
            ),
            "summarization": (
                "Please summarize the key points from this lengthy document.",
                "Here are the main takeaways: The document covers three key areas with specific recommendations for each."
            ),
            "qa": (
                "What are the main benefits of using microservices architecture?",
                "Microservices offer several key benefits: scalability, technology diversity, fault isolation, and easier deployment."
            ),
            "general": (
                cls._random_choice(cls.SAMPLE_USER_QUERIES),
                cls._random_choice(cls.SAMPLE_AI_RESPONSES)
            )
        }

        return purpose_templates.get(purpose, purpose_templates["general"])

    @staticmethod
    def _random_choice(items: List[Any]) -> Any:
        """Simple random choice implementation without importing random"""
        return items[int(time.time() * 1000) % len(items)]

class TraceBuilder:
    """Builds nested trace structures with proper relationships"""

    def __init__(self, posthog_client: Posthog):
        self.posthog_client = posthog_client
        self.events: List[Dict[str, Any]] = []
        self.trace_id = EventGenerator.generate_trace_id()
        self.distinct_id = os.getenv("POSTHOG_DISTINCT_ID", "trace-generator-user")

    def reset(self):
        """Reset the builder for a new trace"""
        self.events = []
        self.trace_id = EventGenerator.generate_trace_id()

    def add_trace_event(self, span_name: str = "chat_completion") -> str:
        """Add a trace event and return the trace ID"""
        event = EventGenerator.generate_trace_event(self.trace_id, span_name)
        self.events.append(event)
        return self.trace_id

    def add_span_event(self, span_name: str, parent_id: Optional[str] = None) -> str:
        """Add a span event and return the span ID"""
        event = EventGenerator.generate_span_event(self.trace_id, span_name, parent_id)
        span_id = event["properties"]["$ai_span_id"]
        self.events.append(event)
        return span_id

    def add_generation_event(self, model: str = "gpt-4o-mini", parent_id: Optional[str] = None) -> str:
        """Add a generation event and return the span ID"""
        event = EventGenerator.generate_generation_event(self.trace_id, model, parent_id)
        span_id = event["properties"]["$ai_span_id"]
        self.events.append(event)
        return span_id

    def add_embedding_event(self, model: str = "text-embedding-3-small", parent_id: Optional[str] = None) -> str:
        """Add an embedding event and return the span ID"""
        event = EventGenerator.generate_embedding_event(self.trace_id, model, parent_id)
        span_id = event["properties"]["$ai_span_id"]
        self.events.append(event)
        return span_id

    def add_custom_generation_event(self, model: str, purpose: str, name: str, parent_id: Optional[str] = None,
                                    user_input: Optional[str] = None, assistant_output: Optional[str] = None) -> str:
        """Add a custom generation event with specific purpose or manual text and return the span ID"""
        event = EventGenerator.generate_custom_generation_event(
            self.trace_id, model, purpose, name, parent_id, user_input, assistant_output
        )
        span_id = event["properties"]["$ai_span_id"]
        self.events.append(event)
        return span_id

    def add_custom_embedding_event(self, model: str, name: str, parent_id: Optional[str] = None) -> str:
        """Add a custom embedding event and return the span ID"""
        event = EventGenerator.generate_custom_embedding_event(self.trace_id, model, name, parent_id)
        span_id = event["properties"]["$ai_span_id"]
        self.events.append(event)
        return span_id

    def build_simple_chat_trace(self, model: str = "gpt-4o-mini", user_input: Optional[str] = None,
                                assistant_output: Optional[str] = None) -> Dict[str, Any]:
        """Build a simple chat conversation trace"""
        self.reset()

        # Add trace event
        self.add_trace_event("simple_chat")

        # Add main generation event with custom text support
        generation_id = self.add_custom_generation_event(
            model=model,
            purpose="general",
            name="chat_completion",
            parent_id=self.trace_id,
            user_input=user_input,
            assistant_output=assistant_output
        )

        return {
            "trace_id": self.trace_id,
            "events_count": len(self.events),
            "structure": "Simple chat with one generation"
        }

    def build_rag_pipeline_trace(self) -> Dict[str, Any]:
        """Build a RAG (Retrieval-Augmented Generation) pipeline trace"""
        self.reset()

        # Add trace event
        self.add_trace_event("rag_pipeline")

        # Add retrieval span
        retrieval_id = self.add_span_event("document_retrieval", self.trace_id)

        # Add embedding for query
        query_embed_id = self.add_embedding_event("text-embedding-3-small", retrieval_id)

        # Add search span
        search_id = self.add_span_event("vector_search", retrieval_id)

        # Add reranking span
        rerank_id = self.add_span_event("document_reranking", retrieval_id)

        # Add generation with context
        generation_id = self.add_generation_event("gpt-4o", self.trace_id)

        return {
            "trace_id": self.trace_id,
            "events_count": len(self.events),
            "structure": "RAG pipeline: retrieval → embedding → search → rerank → generation"
        }

    def build_multiagent_trace(self) -> Dict[str, Any]:
        """Build a multi-step agent trace with tool calls"""
        self.reset()

        # Add trace event
        self.add_trace_event("multiagent_workflow")

        # Planning phase
        planning_id = self.add_span_event("planning_phase", self.trace_id)
        plan_generation_id = self.add_generation_event("gpt-4o", planning_id)

        # Tool execution phase
        execution_id = self.add_span_event("execution_phase", self.trace_id)

        # First tool call
        tool1_id = self.add_span_event("tool_call_weather", execution_id)
        tool1_generation_id = self.add_generation_event("gpt-4o-mini", tool1_id)

        # Second tool call
        tool2_id = self.add_span_event("tool_call_search", execution_id)
        tool2_generation_id = self.add_generation_event("gpt-4o-mini", tool2_id)

        # Final synthesis
        synthesis_id = self.add_span_event("synthesis_phase", self.trace_id)
        final_generation_id = self.add_generation_event("gpt-4o", synthesis_id)

        return {
            "trace_id": self.trace_id,
            "events_count": len(self.events),
            "structure": "Multi-agent: planning → execution (2 tools) → synthesis"
        }

    def build_custom_trace(self, structure: Dict[str, Any]) -> Dict[str, Any]:
        """Build a custom trace based on user-defined structure"""
        self.reset()

        # Add trace event
        trace_name = structure.get("name", "custom_trace")
        self.add_trace_event(trace_name)

        # Process nodes
        node_ids = {}
        for node_config in structure.get("nodes", []):
            node_type = node_config["type"]
            node_name = node_config["name"]
            parent_name = node_config.get("parent")
            parent_id = node_ids.get(parent_name, self.trace_id)

            if node_type == "span":
                node_id = self.add_span_event(node_name, parent_id)
                node_ids[node_name] = node_id

            elif node_type == "generation":
                model = node_config.get("model", "gpt-4o-mini")
                purpose = node_config.get("purpose", "general")
                user_input = node_config.get("user_input")
                assistant_output = node_config.get("assistant_output")
                node_id = self.add_custom_generation_event(
                    model, purpose, node_name, parent_id, user_input, assistant_output
                )
                node_ids[node_name] = node_id

            elif node_type == "embedding":
                model = node_config.get("model", "text-embedding-3-small")
                node_id = self.add_custom_embedding_event(model, node_name, parent_id)
                node_ids[node_name] = node_id

        return {
            "trace_id": self.trace_id,
            "events_count": len(self.events),
            "structure": f"Custom trace: {trace_name}"
        }

    def send_events(self):
        """Send all accumulated events to PostHog"""
        if not self.events:
            print("❌ No events to send")
            return

        print(f"\n📤 Sending {len(self.events)} events to PostHog...")

        try:
            successful_sends = 0
            for event in self.events:
                try:
                    self.posthog_client.capture(
                        distinct_id=self.distinct_id,
                        event=event["event"],
                        properties=event["properties"],
                        timestamp=event.get("timestamp")
                    )
                    successful_sends += 1
                except Exception as send_error:
                    print(f"⚠️  Failed to send event {event['event']}: {str(send_error)}")

            if successful_sends == len(self.events):
                print(f"✅ Successfully sent trace with ID: {self.trace_id}")
                print(f"   Events sent: {successful_sends}/{len(self.events)}")
            else:
                print(f"⚠️  Partially sent trace with ID: {self.trace_id}")
                print(f"   Events sent: {successful_sends}/{len(self.events)}")

        except Exception as error:
            print(f"❌ Failed to send events: {str(error)}")
            print("💡 Check your PostHog configuration and network connection")

    def get_event_summary(self) -> Dict[str, int]:
        """Get a summary of events by type"""
        summary = {}
        for event in self.events:
            event_type = event["event"]
            summary[event_type] = summary.get(event_type, 0) + 1
        return summary

class TraceGenerator:
    """Main CLI application for interactive trace generation"""

    def __init__(self):
        # Validate environment variables
        if not self.validate_environment():
            print("❌ Environment validation failed. Please check your .env file.")
            exit(1)

        # Initialize PostHog client
        try:
            self.posthog = Posthog(
                os.getenv("POSTHOG_API_KEY"),
                host=os.getenv("POSTHOG_HOST", "https://app.posthog.com")
            )
            self.builder = TraceBuilder(self.posthog)
            print("✅ PostHog client initialized successfully")
        except Exception as error:
            print(f"❌ Failed to initialize PostHog client: {str(error)}")
            exit(1)

    def validate_environment(self) -> bool:
        """Validate required environment variables"""
        required_vars = ["POSTHOG_API_KEY"]
        missing_vars = []

        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)

        if missing_vars:
            print("❌ Missing required environment variables:")
            for var in missing_vars:
                print(f"   - {var}")
            print("\n💡 Please add these to your .env file")
            return False

        # Check if API key looks valid (basic format check)
        api_key = os.getenv("POSTHOG_API_KEY")
        if len(api_key) < 10:
            print("❌ POSTHOG_API_KEY appears to be invalid (too short)")
            return False

        return True

    def clear_screen(self):
        """Clear the terminal screen"""
        if os.getenv('DEBUG') != '1':
            os.system('cls' if platform.system() == 'Windows' else 'clear')

    def display_banner(self):
        """Display the application banner"""
        print("\n🎯 Interactive LLM Trace Generator")
        print("=" * 50)
        print("Create complex nested trace data for PostHog analytics")
        print("Perfect for testing LLM observability features")
        print("=" * 50)

    def main_menu(self):
        """Display main menu and handle user choice"""
        while True:
            self.clear_screen()
            self.display_banner()

            print("\n📋 Main Menu:")
            print("  1. 💬 Simple Chat Trace")
            print("  2. 🔍 RAG Pipeline Trace")
            print("  3. 🤖 Multi-step Agent Trace")
            print("  4. 🎨 Custom Trace Builder")
            print("  5. 📊 View Last Generated Trace")
            print("  6. ❌ Exit")

            try:
                choice = input("\nSelect an option (1-6): ").strip()

                if choice == "1":
                    self.create_simple_chat_trace()
                elif choice == "2":
                    self.create_rag_pipeline_trace()
                elif choice == "3":
                    self.create_multiagent_trace()
                elif choice == "4":
                    self.create_custom_trace()
                elif choice == "5":
                    self.view_last_trace()
                elif choice == "6":
                    print("\n👋 Goodbye!")
                    break
                else:
                    print("❌ Invalid choice. Please select 1-6.")
                    input("Press Enter to continue...")

            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break

    def create_simple_chat_trace(self):
        """Create a simple chat interaction trace"""
        print("\n💬 Creating Simple Chat Trace...")
        print("This creates a basic conversation with user input and AI response")

        try:
            # Ask if they want to customize the generation
            customize = input("\nCustomize generation text? (y/n, default: n): ").strip().lower()

            user_input = None
            assistant_output = None
            model = "gpt-4o-mini"

            if customize in ["y", "yes"]:
                print("\nEnter custom text for the generation:")
                user_input = input("User input: ").strip()
                assistant_output = input("Assistant output: ").strip()

                if not user_input or not assistant_output:
                    print("⚠️  Both fields required for custom text. Using preset generation.")
                    user_input = None
                    assistant_output = None

            # Ask for model
            models = ["gpt-4o", "gpt-4o-mini", "claude-3-sonnet", "claude-3-haiku"]
            print(f"\nAvailable models: {', '.join(models)}")
            model_choice = input("Model (default: gpt-4o-mini): ").strip()
            if model_choice in models:
                model = model_choice

            result = self.builder.build_simple_chat_trace(model, user_input, assistant_output)
            self.display_trace_summary(result)

            if self.confirm_send():
                self.builder.send_events()
            else:
                print("❌ Trace not sent")

        except Exception as error:
            print(f"❌ Error creating trace: {str(error)}")

        input("\nPress Enter to continue...")

    def create_rag_pipeline_trace(self):
        """Create a RAG (Retrieval-Augmented Generation) pipeline trace"""
        print("\n🔍 Creating RAG Pipeline Trace...")
        print("This creates a trace with document retrieval, reranking, and generation")

        try:
            result = self.builder.build_rag_pipeline_trace()
            self.display_trace_summary(result)

            if self.confirm_send():
                self.builder.send_events()
            else:
                print("❌ Trace not sent")

        except Exception as error:
            print(f"❌ Error creating trace: {str(error)}")

        input("\nPress Enter to continue...")

    def create_multiagent_trace(self):
        """Create a multi-step agent trace"""
        print("\n🤖 Creating Multi-step Agent Trace...")
        print("This creates a complex trace with multiple tool calls and reasoning steps")

        try:
            result = self.builder.build_multiagent_trace()
            self.display_trace_summary(result)

            if self.confirm_send():
                self.builder.send_events()
            else:
                print("❌ Trace not sent")

        except Exception as error:
            print(f"❌ Error creating trace: {str(error)}")

        input("\nPress Enter to continue...")

    def create_custom_trace(self):
        """Interactive custom trace builder"""
        print("\n🎨 Custom Trace Builder...")
        print("Build your own trace structure step by step")

        try:
            structure = self.build_custom_structure()
            if structure:
                result = self.builder.build_custom_trace(structure)
                self.display_trace_summary(result)

                if self.confirm_send():
                    self.builder.send_events()
                else:
                    print("❌ Trace not sent")
            else:
                print("❌ No custom structure defined")

        except Exception as error:
            print(f"❌ Error creating custom trace: {str(error)}")

        input("\nPress Enter to continue...")

    def build_custom_structure(self) -> Optional[Dict[str, Any]]:
        """Interactive builder for custom trace structure"""
        print("\n🏗️ Custom Trace Structure Builder")
        print("=" * 40)

        # Get trace name
        trace_name = input("Enter trace name (default: custom_trace): ").strip()
        if not trace_name:
            trace_name = "custom_trace"

        # Initialize tree with trace as root
        tree = {
            "type": "trace",
            "name": trace_name,
            "children": []
        }

        while True:
            self.display_tree(tree)
            print("\nOptions:")
            print("  1. Add child to a node")
            print("  2. Finish and create trace")
            print("  3. Cancel")

            choice = input("Select option (1-3): ").strip()

            if choice == "1":
                self.add_child_to_node(tree)
            elif choice == "2":
                return self.convert_tree_to_structure(tree)
            elif choice == "3":
                return None
            else:
                print("❌ Invalid choice")

    def display_tree(self, tree: Dict[str, Any], indent: int = 0):
        """Display the current tree structure"""
        print(f"\n🌳 Current Structure:")
        self._display_node(tree, indent)

    def _display_node(self, node: Dict[str, Any], indent: int = 0):
        """Recursively display a node and its children"""
        prefix = "  " * indent
        node_type = node["type"]
        name = node["name"]

        # Add type-specific icons
        if node_type == "trace":
            icon = "🎯"
        elif node_type == "span":
            icon = "📦"
        elif node_type == "generation":
            icon = "🤖"
        elif node_type == "embedding":
            icon = "🔢"
        else:
            icon = "❓"

        # Display additional info for generations
        extra_info = ""
        if node_type == "generation":
            model = node.get("model", "gpt-4o-mini")
            purpose = node.get("purpose", "general")
            extra_info = f" (model: {model}, purpose: {purpose})"

        print(f"{prefix}{icon} {node_type}: {name}{extra_info}")

        # Display children
        for child in node.get("children", []):
            self._display_node(child, indent + 1)

    def add_child_to_node(self, tree: Dict[str, Any]):
        """Add a child to a selected node"""
        # Get available parents (nodes that can have children)
        available_parents = self._get_available_parents(tree)

        if not available_parents:
            print("❌ No nodes can have children (generations and embeddings are leaves)")
            return

        print("\nAvailable parent nodes:")
        for i, (path, node) in enumerate(available_parents):
            node_type = node["type"]
            name = node["name"]
            print(f"  {i+1}. {node_type}: {name}")

        try:
            parent_choice = int(input(f"Select parent (1-{len(available_parents)}): ")) - 1
            if parent_choice < 0 or parent_choice >= len(available_parents):
                print("❌ Invalid parent selection")
                return
        except ValueError:
            print("❌ Invalid input")
            return

        parent_path, parent_node = available_parents[parent_choice]

        # Get valid child types for this parent
        valid_child_types = self._get_valid_child_types(parent_node["type"])

        print(f"\nValid child types for {parent_node['type']}:")
        for i, child_type in enumerate(valid_child_types):
            print(f"  {i+1}. {child_type}")

        try:
            type_choice = int(input(f"Select child type (1-{len(valid_child_types)}): ")) - 1
            if type_choice < 0 or type_choice >= len(valid_child_types):
                print("❌ Invalid type selection")
                return
        except ValueError:
            print("❌ Invalid input")
            return

        child_type = valid_child_types[type_choice]

        # Configure the new child
        child_config = self.configure_node(child_type)
        if child_config:
            parent_node["children"].append(child_config)
            print(f"✅ Added {child_type}: {child_config['name']}")

    def _get_available_parents(self, tree: Dict[str, Any]) -> List[tuple]:
        """Get all nodes that can have children"""
        available = []
        self._collect_available_parents(tree, "", available)
        return available

    def _collect_available_parents(self, node: Dict[str, Any], path: str, available: List[tuple]):
        """Recursively collect nodes that can have children"""
        node_type = node["type"]

        # Only trace and span can have children
        if node_type in ["trace", "span"]:
            current_path = f"{path}/{node['name']}" if path else node["name"]
            available.append((current_path, node))

        # Recurse into children
        for child in node.get("children", []):
            child_path = f"{path}/{node['name']}" if path else node["name"]
            self._collect_available_parents(child, child_path, available)

    def _get_valid_child_types(self, parent_type: str) -> List[str]:
        """Get valid child types for a parent node type"""
        if parent_type == "trace":
            return ["span", "generation", "embedding"]
        elif parent_type == "span":
            return ["span", "generation", "embedding"]
        else:
            return []  # generations and embeddings are leaves

    def configure_node(self, node_type: str) -> Optional[Dict[str, Any]]:
        """Configure a new node based on its type"""
        print(f"\n➕ Adding New {node_type.title()}")
        print("-" * 25)

        # Get node name
        node_name = input(f"{node_type.title()} name: ").strip()
        if not node_name:
            print(f"❌ {node_type.title()} name is required")
            return None

        config = {
            "type": node_type,
            "name": node_name,
            "children": []
        }

        # Type-specific configuration
        if node_type == "generation":
            config.update(self.configure_generation())
        elif node_type == "embedding":
            config.update(self.configure_embedding())
        # spans don't need additional configuration

        return config

    def configure_generation(self) -> Dict[str, Any]:
        """Configure generation-specific properties"""
        # Get purpose (including custom as a peer option)
        purposes = [
            "general", "planning", "tool_call", "synthesis",
            "reasoning", "code_generation", "summarization", "qa", "custom"
        ]

        print(f"\nGeneration purposes: {', '.join(purposes)}")
        purpose = input("Purpose (default: general): ").strip()
        if not purpose or purpose not in purposes:
            purpose = "general"

        # Get model
        models = ["gpt-4o", "gpt-4o-mini", "claude-3-sonnet", "claude-3-haiku"]
        print(f"\nAvailable models: {', '.join(models)}")
        model = input("Model (default: gpt-4o-mini): ").strip()
        if not model or model not in models:
            model = "gpt-4o-mini"

        # If custom, prompt for manual text
        if purpose == "custom":
            print("\nEnter custom text for this generation:")
            user_input = input("User input: ").strip()
            assistant_output = input("Assistant output: ").strip()

            if not user_input or not assistant_output:
                print("⚠️  Both user input and assistant output are required. Using defaults.")
                user_input = "Sample user query"
                assistant_output = "Sample assistant response"

            return {
                "model": model,
                "user_input": user_input,
                "assistant_output": assistant_output
            }
        else:
            return {
                "purpose": purpose,
                "model": model
            }

    def configure_embedding(self) -> Dict[str, Any]:
        """Configure embedding-specific properties"""
        # Get model
        models = ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"]
        print(f"\nAvailable embedding models: {', '.join(models)}")
        model = input("Model (default: text-embedding-3-small): ").strip()
        if not model or model not in models:
            model = "text-embedding-3-small"

        return {"model": model}

    def convert_tree_to_structure(self, tree: Dict[str, Any]) -> Dict[str, Any]:
        """Convert the tree structure to the format expected by build_custom_trace"""
        structure = {
            "name": tree["name"],
            "nodes": []
        }

        self._flatten_tree(tree, structure["nodes"], None)
        return structure

    def _flatten_tree(self, node: Dict[str, Any], nodes: List[Dict[str, Any]], parent_name: Optional[str]):
        """Flatten tree structure for processing"""
        if node["type"] != "trace":  # Don't include the trace itself as a node
            node_config = {
                "type": node["type"],
                "name": node["name"]
            }

            if parent_name:
                node_config["parent"] = parent_name

            # Add type-specific properties
            if node["type"] == "generation":
                node_config["model"] = node.get("model", "gpt-4o-mini")
                # Preserve manual text if provided, otherwise use purpose
                if "user_input" in node and "assistant_output" in node:
                    node_config["user_input"] = node["user_input"]
                    node_config["assistant_output"] = node["assistant_output"]
                else:
                    node_config["purpose"] = node.get("purpose", "general")
            elif node["type"] == "embedding":
                node_config["model"] = node.get("model", "text-embedding-3-small")

            nodes.append(node_config)

        # Recurse into children
        current_name = node["name"] if node["type"] != "trace" else None
        for child in node.get("children", []):
            self._flatten_tree(child, nodes, current_name)

    def display_trace_summary(self, result: Dict[str, Any]):
        """Display a summary of the created trace"""
        print(f"\n📊 Trace Summary")
        print("=" * 30)
        print(f"Trace ID: {result['trace_id']}")
        print(f"Total Events: {result['events_count']}")
        print(f"Structure: {result['structure']}")

        # Show event breakdown
        summary = self.builder.get_event_summary()
        if summary:
            print("\nEvent Breakdown:")
            for event_type, count in summary.items():
                print(f"  {event_type}: {count}")

    def confirm_send(self) -> bool:
        """Ask user to confirm sending the trace"""
        while True:
            choice = input("\n📤 Send this trace to PostHog? (y/n): ").strip().lower()
            if choice in ["y", "yes"]:
                return True
            elif choice in ["n", "no"]:
                return False
            else:
                print("❌ Please enter 'y' or 'n'")

    def view_last_trace(self):
        """Display information about the last generated trace"""
        if not self.builder.events:
            print("\n📊 No trace has been generated yet.")
        else:
            print(f"\n📊 Last Generated Trace")
            print(f"Trace ID: {self.builder.trace_id}")
            print(f"Events: {len(self.builder.events)}")

            # Show event summary
            event_types = {}
            for event in self.builder.events:
                event_type = event["event"]
                event_types[event_type] = event_types.get(event_type, 0) + 1

            print("\nEvent Summary:")
            for event_type, count in event_types.items():
                print(f"  {event_type}: {count}")

        input("\nPress Enter to continue...")

def main():
    """Main application entry point"""
    app = TraceGenerator()
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        result = app.builder.build_simple_chat_trace("gpt-4o-mini")
        app.display_trace_summary(result)
        app.builder.send_events()
        return

    if not sys.stdin.isatty():
        print("Non-interactive stdin detected. Running quick trace generation.")
        result = app.builder.build_simple_chat_trace("gpt-4o-mini")
        app.display_trace_summary(result)
        app.builder.send_events()
        return

    app.main_menu()

if __name__ == "__main__":
    main()
