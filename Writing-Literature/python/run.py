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

class WritingSystem:
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

    def run_mission(self, user_content, writing_params):
        """
        Main entry point for the writing workflow.
        
        Args:
            user_content: The raw content to process (text, file path, or dict with source info)
            writing_params: Dictionary with keys like 'style', 'length', 'tone', 'format'
        """
        # Master System Prompt combines Director Identity + Global Config
        system_msg = f"{self.agents['orchestrator']}\n\nGLOBAL_CONFIG: {json.dumps(self.config)}"
        
        # Build initial user prompt with content and parameters
        initial_prompt = f"""
Content to Process:
{user_content}

Writing Parameters:
{json.dumps(writing_params, indent=2)}

Begin the writing workflow: INGEST → COMPRESS → EXPAND → REVIEW
"""
        
        messages = [{"role": "user", "content": initial_prompt}]
        
        print(f"🚀 Writing Mission Started")
        print(f"📝 Target Style: {writing_params.get('style', 'Not specified')}")
        print(f"📏 Target Length: {writing_params.get('length', 'Not specified')} words")
        print(f"🤖 Model Provider: {self.provider}")

        for loop_num in range(self.max_loops):
            if self.provider == 'gemini':
                response = self._call_gemini(system_msg, messages)
            else:
                response = self._call_anthropic(system_msg, messages)

            if response.get('tool_use'):
                tool_use = response['tool_use']
                print(f"📦 Agent Activity [{loop_num+1}/{self.max_loops}]: {tool_use['name']}")

                # Simulate tool execution (expand this for real implementation)
                result = self._execute_tool(tool_use['name'], tool_use['input'])

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
                # Final response received
                print(f"✅ Writing Mission Complete (Loops: {loop_num+1})")
                return response['text']

        # Loop limit reached
        print(f"⚠️  Loop limit reached ({self.max_loops}). Returning partial result.")
        return "ERROR: Maximum iteration limit reached. Partial output may be available in previous messages."

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

    def _execute_tool(self, tool_name, tool_input):
        """
        Simulates tool execution. Expand this for real tool implementations.
        """
        if tool_name == "word_counter":
            text = tool_input.get("text", "")
            word_count = len(text.split())
            char_count = len(text)
            return json.dumps({
                "word_count": word_count,
                "character_count": char_count,
                "estimated_reading_time_minutes": round(word_count / 200, 1)
            })
        
        elif tool_name == "content_ingestion":
            source_type = tool_input.get("source_type")
            if source_type == "text":
                return json.dumps({"status": "success", "content": tool_input.get("content", "")})
            elif source_type == "file":
                # Simulate file reading
                return json.dumps({"status": "success", "content": "File content would be loaded here"})
            else:
                return json.dumps({"status": "error", "message": "Unsupported source type"})
        
        else:
            return json.dumps({"status": "simulated", "message": f"Tool {tool_name} executed successfully"})


if __name__ == "__main__":
    # Example usage
    system = WritingSystem()
    
    sample_content = """
    Artificial intelligence has transformed modern computing. Machine learning algorithms 
    can now process vast amounts of data. Neural networks mimic human brain function. 
    Deep learning enables computers to recognize patterns. AI applications include 
    image recognition, natural language processing, and autonomous vehicles.
    """
    
    params = {
        "style": "professional",
        "length": 500,
        "tone": "informative",
        "format": "article with introduction and conclusion"
    }
    
    result = system.run_mission(sample_content, params)
    print("\n" + "="*80)
    print("FINAL OUTPUT:")
    print("="*80)
    print(result)
