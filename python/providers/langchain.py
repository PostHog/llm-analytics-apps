import os
from posthog.ai.langchain import CallbackHandler
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage, SystemMessage
from posthog import Posthog
from .base import BaseProvider
from .constants import OPENAI_CHAT_MODEL, OPENAI_VISION_MODEL, SYSTEM_PROMPT_ASSISTANT

class LangChainProvider(BaseProvider):
    def __init__(self, posthog_client: Posthog):
        super().__init__(posthog_client)
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        
        self.callback_handler = CallbackHandler(
            client=posthog_client
        )
        
        # Store conversation history in LangChain's native format
        self.langchain_messages = [
            SystemMessage(content=SYSTEM_PROMPT_ASSISTANT)
        ]
        
        self._setup_chain()
    
    def get_tool_definitions(self):
        """Return tool definitions (not used by LangChain but required by base)"""
        return []
    
    def _setup_chain(self):
        """Setup the LangChain chain with tools"""
        @tool
        def get_weather(latitude: float, longitude: float, location_name: str) -> str:
            """Get the current weather for a specific location using geographical coordinates.

            Args:
                latitude: The latitude of the location (e.g., 37.7749 for San Francisco)
                longitude: The longitude of the location (e.g., -122.4194 for San Francisco)
                location_name: A human-readable name for the location (e.g., 'San Francisco, CA' or 'Dublin, Ireland')

            Returns:
                Weather information for the specified location
            """
            return self.get_weather(latitude, longitude, location_name)
        
        self.langchain_tools = [get_weather]
        self.tool_map = {tool.name: tool for tool in self.langchain_tools}
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT_ASSISTANT),
            ("user", "{input}")
        ])
        
        model = ChatOpenAI(openai_api_key=self.OPENAI_API_KEY, temperature=0)
        self.chain = prompt | model.bind_tools(self.langchain_tools)
    
    def get_name(self):
        return "LangChain (OpenAI)"
    
    def get_description(self):
        return "💡 You can ask me about the weather!"
    
    def reset_conversation(self):
        """Reset the conversation history"""
        self.langchain_messages = [
            SystemMessage(content=SYSTEM_PROMPT_ASSISTANT)
        ]
        self.messages = []
    
    def chat(self, user_input: str, base64_image: str = None) -> str:
        """Send a message to LangChain and get response"""
        # Add user message to history
        if base64_image:
            # Create a message with image content
            user_message = HumanMessage(content=[
                {
                    "type": "text",
                    "text": user_input
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    }
                }
            ])
        else:
            user_message = HumanMessage(content=user_input)
        self.langchain_messages.append(user_message)
        
        # Use the model directly with conversation history instead of the chain
        # Use vision model for images
        model_name = OPENAI_VISION_MODEL if base64_image else OPENAI_CHAT_MODEL
        model = ChatOpenAI(openai_api_key=self.OPENAI_API_KEY, temperature=0, model_name=model_name)
        model_with_tools = model.bind_tools(self.langchain_tools)

        # Prepare API request parameters
        request_params = {
            "input": self.langchain_messages,
            "config": {"callbacks": [self.callback_handler]}
        }

        response = model_with_tools.invoke(**request_params)

        # Debug: Log the API call (request + response)
        self._debug_api_call("LangChain (OpenAI)", request_params, response)

        # Collect display parts
        display_parts = []
        
        # Add the AI's text response to display (if any)
        if response.content:
            display_parts.append(response.content)
        
        # Check if the model wants to use tools
        if response.tool_calls:
            # Execute tool calls
            tool_messages = []
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                
                # Execute the tool
                if tool_name in self.tool_map:
                    tool_result = self.tool_map[tool_name].invoke(tool_args)
                    tool_result_text = self.format_tool_result("get_weather", tool_result)
                    display_parts.append(tool_result_text)
                    
                    tool_messages.append(
                        ToolMessage(
                            content=str(tool_result),
                            tool_call_id=tool_call["id"],
                        )
                    )
        
        # Add assistant's response to conversation history
        self.langchain_messages.append(response)
        
        # Add tool messages to history if any
        if response.tool_calls:
            self.langchain_messages.extend(tool_messages)
        
        return "\n\n".join(display_parts) if display_parts else "No response received"