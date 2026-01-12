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
        
        for loop_num in range(self.max_loops):
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=8000,
                system=system_msg,
                tools=self.tools,
                messages=messages
            )

            if response.stop_reason == "tool_use":
                tool_use = next(block for block in response.content if block.type == "tool_use")
                print(f"📦 Agent Activity [{loop_num+1}/{self.max_loops}]: {tool_use.name}")
                
                # Simulate tool execution (expand this for real implementation)
                result = self._execute_tool(tool_use.name, tool_use.input)
                
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user", 
                    "content": [{"type": "tool_result", "tool_use_id": tool_use.id, "content": result}]
                })
            else:
                # Final response received
                print(f"✅ Writing Mission Complete (Loops: {loop_num+1})")
                return response.content[0].text
        
        # Loop limit reached
        print(f"⚠️  Loop limit reached ({self.max_loops}). Returning partial result.")
        return "ERROR: Maximum iteration limit reached. Partial output may be available in previous messages."

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
