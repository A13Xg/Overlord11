import os
import json
import anthropic
from pathlib import Path
from dotenv import load_dotenv

# 1. Setup Paths (Navigating from /python/run.py to Parent)
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR.parent / ".env"  # Points to Overlord11/.env
load_dotenv(dotenv_path=ENV_PATH)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

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
        
        for _ in range(self.max_loops):
            response = client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=4000,
                system=system_msg,
                tools=self.tools,
                messages=messages
            )

            if response.stop_reason == "tool_use":
                tool_use = next(block for block in response.content if block.type == "tool_use")
                print(f"📦 Agent Activity: {tool_use.name}")
                
                # Note: You would expand this to handle your file_tool and search_tool
                result = "Simulated tool success." 
                
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user", 
                    "content": [{"type": "tool_result", "tool_use_id": tool_use.id, "content": result}]
                })
            else:
                return response.content[0].text