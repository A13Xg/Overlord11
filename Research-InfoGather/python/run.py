import os
import json
import anthropic
import google.generativeai as genai
from pathlib import Path
from dotenv import load_dotenv

# 1. Setup Paths (Navigating from /python/run.py to Parent)
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR.parent / ".env"  # Points to Overlord11/.env
load_dotenv(dotenv_path=ENV_PATH)


def get_model_client(config):
    """Initialize the appropriate model client based on config."""
    model_config = config.get('model_config', {})
    provider = model_config.get('provider', 'anthropic')

    if provider == 'gemini':
        api_key = os.getenv(model_config['models']['gemini']['env_var'])
        genai.configure(api_key=api_key)
        return 'gemini', genai.GenerativeModel(model_config['models']['gemini']['model_name'])
    else:
        api_key = os.getenv(model_config['models']['anthropic']['env_var'])
        return 'anthropic', anthropic.Anthropic(api_key=api_key)

class ResearchSystem:
    def __init__(self):
        self.config_path = BASE_DIR / "config.json"
        with open(self.config_path, 'r') as f:
            self.config = json.load(f)

        self.agents_dir = BASE_DIR / "agents"
        self.tools_dir = BASE_DIR / "tools"

        self.agents = self.load_markdown_assets()
        self.tools = self.load_json_assets()
        self.max_loops = self.config['orchestration_logic']['max_loops']

        # Initialize model client based on config
        self.provider, self.client = get_model_client(self.config)
        self.model_config = self.config.get('model_config', {})

    def load_markdown_assets(self):
        assets = {}
        for file in os.listdir(self.agents_dir):
            if file.endswith(".md"):
                with open(self.agents_dir / file, 'r') as f:
                    assets[file.replace(".md", "")] = f.read()
        return assets

    def load_json_assets(self):
        tools = []
        for file in os.listdir(self.tools_dir):
            if file.endswith(".json"):
                with open(self.tools_dir / file, 'r') as f:
                    tools.append(json.load(f))
        return tools

    def run_mission(self, user_prompt):
        # Master System Prompt combines Director Identity + Global Config
        system_msg = f"{self.agents['orchestrator']}\n\nGLOBAL_CONFIG: {json.dumps(self.config)}"

        messages = [{"role": "user", "content": user_prompt}]

        print(f"🚀 Mission Started: {user_prompt}")
        print(f"🤖 Model Provider: {self.provider}")

        for loop_num in range(self.max_loops):
            if self.provider == 'gemini':
                response = self._call_gemini(system_msg, messages)
            else:
                response = self._call_anthropic(system_msg, messages)

            if response.get('tool_use'):
                tool_use = response['tool_use']
                print(f"📦 Agent Activity [{loop_num+1}/{self.max_loops}]: {tool_use['name']}")

                # Note: You would expand this to handle your file_tool and search_tool
                result = "Simulated tool success."

                if self.provider == 'anthropic':
                    messages.append({"role": "assistant", "content": response['raw_content']})
                    messages.append({
                        "role": "user",
                        "content": [{"type": "tool_result", "tool_use_id": tool_use['id'], "content": result}]
                    })
                else:
                    messages.append({"role": "assistant", "content": f"Tool call: {tool_use['name']}"})
                    messages.append({"role": "user", "content": f"Tool result: {result}"})
            else:
                print(f"✅ Research Mission Complete (Loops: {loop_num+1})")
                return response['text']

        print(f"⚠️  Loop limit reached ({self.max_loops})")
        return "ERROR: Maximum iteration limit reached."

    def _call_anthropic(self, system_msg, messages):
        """Call Anthropic API."""
        model_name = self.model_config['models']['anthropic']['model_name']
        max_tokens = self.model_config['models']['anthropic']['max_tokens']

        response = self.client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            system=system_msg,
            tools=self.tools,
            messages=messages
        )

        if response.stop_reason == "tool_use":
            tool_use = next(block for block in response.content if block.type == "tool_use")
            return {
                'tool_use': {'name': tool_use.name, 'input': tool_use.input, 'id': tool_use.id},
                'raw_content': response.content
            }
        else:
            return {'text': response.content[0].text, 'tool_use': None}

    def _call_gemini(self, system_msg, messages):
        """Call Google Gemini API."""
        # Build conversation for Gemini
        full_prompt = f"{system_msg}\n\n"
        for msg in messages:
            role = msg['role']
            content = msg['content'] if isinstance(msg['content'], str) else json.dumps(msg['content'])
            full_prompt += f"{role.upper()}: {content}\n\n"

        # Add tool descriptions to prompt
        tool_desc = "Available tools:\n" + json.dumps(self.tools, indent=2)
        full_prompt += f"\n{tool_desc}\n\nIf you need to use a tool, respond with JSON: {{\"tool\": \"tool_name\", \"input\": {{...}}}}\nOtherwise, provide your final response."

        response = self.client.generate_content(full_prompt)
        response_text = response.text

        # Check if response is a tool call
        try:
            if '{"tool"' in response_text:
                tool_json = json.loads(response_text.strip())
                if 'tool' in tool_json:
                    return {
                        'tool_use': {'name': tool_json['tool'], 'input': tool_json.get('input', {}), 'id': 'gemini_tool'},
                        'raw_content': response_text
                    }
        except json.JSONDecodeError:
            pass

        return {'text': response_text, 'tool_use': None}