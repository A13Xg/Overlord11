import os
import json
import anthropic
import google.generativeai as genai
from pathlib import Path
from dotenv import load_dotenv

# Setup Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR.parent / ".env"
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

class AnalysisSystem:
    def __init__(self):
        self.config_path = BASE_DIR / "config.json"
        with open(self.config_path, 'r') as f:
            self.config = json.load(f)

        self.agents_dir = BASE_DIR / "agents"
        self.tools_dir = BASE_DIR / "tools"
        self.output_dir = BASE_DIR / "output"

        # Create output directory if it doesn't exist
        self.output_dir.mkdir(exist_ok=True)

        self.agents = self.load_markdown_assets()
        self.tools = self.load_json_assets()
        self.max_loops = self.config['orchestration_logic']['max_loops']

        # Initialize model client based on config
        self.provider, self.client = get_model_client(self.config)
        self.model_config = self.config.get('model_config', {})

        # Check if external APIs are configured
        self.external_apis_enabled = self._check_external_apis()

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

    def _check_external_apis(self):
        """Check if external API keys are configured."""
        api_config = self.config.get('external_apis', {})
        enabled_apis = {
            name: bool(os.getenv(api_info.get('env_var', ''))) 
            for name, api_info in api_config.items()
        }
        return enabled_apis

    def run_mission(self, input_data, output_specs):
        """
        Main entry point for analysis workflow.
        
        Args:
            input_data: The data to analyze (text, file path, or dict with source info)
            output_specs: Dictionary with keys like:
                - 'format': Output format (summary, csv, pdf, chart, etc.)
                - 'type': Specific output type
                - 'options': Format-specific options
                - 'analysis': Type of analysis to perform
        """
        # Build system message with orchestrator + config
        system_msg = f"""{self.agents['orchestrator']}

GLOBAL_CONFIG: {json.dumps(self.config, indent=2)}

EXTERNAL_APIS_STATUS: {json.dumps(self.external_apis_enabled, indent=2)}
"""
        
        # Initial user prompt
        initial_prompt = f"""
Data to Analyze:
{json.dumps(input_data) if isinstance(input_data, dict) else input_data}

Output Specifications:
{json.dumps(output_specs, indent=2)}

External APIs Available: {', '.join([k for k, v in self.external_apis_enabled.items() if v]) or 'None (using internal capabilities only)'}

Begin the analysis workflow: INGEST → ANALYZE → FORMAT → RENDER → VALIDATE
"""
        
        messages = [{"role": "user", "content": initial_prompt}]
        
        print(f"🚀 Analysis Mission Started")
        print(f"📊 Output Format: {output_specs.get('format', 'Not specified')}")
        print(f"🔧 External APIs: {'Enabled' if any(self.external_apis_enabled.values()) else 'Disabled (internal only)'}")
        print(f"🤖 Model Provider: {self.provider}")

        for loop_num in range(self.max_loops):
            if self.provider == 'gemini':
                response = self._call_gemini(system_msg, messages)
            else:
                response = self._call_anthropic(system_msg, messages)

            if response.get('tool_use'):
                tool_use = response['tool_use']
                print(f"📦 Agent Activity [{loop_num+1}/{self.max_loops}]: {tool_use['name']}")

                # Execute tool
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
                # Final response
                print(f"✅ Analysis Mission Complete (Loops: {loop_num+1})")
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

    def _execute_tool(self, tool_name, tool_input):
        """Execute tools with actual implementations where possible."""
        
        if tool_name == "data_ingestion":
            return self._handle_data_ingestion(tool_input)
        
        elif tool_name == "analysis_engine":
            return self._handle_analysis(tool_input)
        
        elif tool_name == "format_converter":
            return self._handle_format_conversion(tool_input)
        
        elif tool_name == "visualization_generator":
            return self._handle_visualization(tool_input)
        
        elif tool_name == "document_renderer":
            return self._handle_document_rendering(tool_input)
        
        elif tool_name == "file_management":
            return self._handle_file_operations(tool_input)
        
        else:
            return json.dumps({"status": "simulated", "message": f"Tool {tool_name} executed"})

    def _handle_data_ingestion(self, params):
        """Handle data ingestion from various sources."""
        source_type = params.get("source_type")
        
        if source_type == "text":
            content = params.get("content", "")
            return json.dumps({
                "status": "success",
                "content": content,
                "length": len(content),
                "type": "text"
            })
        
        elif source_type == "file":
            file_path = params.get("source_path", "")
            try:
                # Try to read file
                full_path = BASE_DIR / "input" / file_path
                if full_path.exists():
                    with open(full_path, 'r') as f:
                        content = f.read()
                    return json.dumps({
                        "status": "success",
                        "content": content,
                        "length": len(content),
                        "type": "file"
                    })
                else:
                    return json.dumps({
                        "status": "error",
                        "message": f"File not found: {file_path}"
                    })
            except Exception as e:
                return json.dumps({
                    "status": "error",
                    "message": str(e)
                })
        
        return json.dumps({"status": "simulated", "message": "Data ingestion simulated"})

    def _handle_analysis(self, params):
        """Handle various analysis operations."""
        analysis_type = params.get("analysis_type")
        data = params.get("data", "")
        
        # Simulate analysis results
        results = {
            "status": "success",
            "analysis_type": analysis_type,
            "findings": f"Analysis of type '{analysis_type}' completed",
            "metadata": {
                "data_length": len(data),
                "timestamp": "2026-01-12"
            }
        }
        
        return json.dumps(results)

    def _handle_format_conversion(self, params):
        """Handle format conversions."""
        input_fmt = params.get("input_format")
        output_fmt = params.get("output_format")
        data = params.get("data", "")
        
        return json.dumps({
            "status": "success",
            "converted_from": input_fmt,
            "converted_to": output_fmt,
            "output": data,  # In real implementation, do actual conversion
            "message": f"Converted from {input_fmt} to {output_fmt}"
        })

    def _handle_visualization(self, params):
        """Handle visualization generation."""
        viz_type = params.get("viz_type")
        output_format = params.get("output_format", "png")
        use_external = params.get("use_external_api", False)
        
        # Determine rendering method
        if use_external and any(self.external_apis_enabled.values()):
            method = "external_api"
        else:
            method = "internal_library"
        
        output_file = f"visualization_{viz_type}.{output_format}"
        
        return json.dumps({
            "status": "success",
            "viz_type": viz_type,
            "output_format": output_format,
            "rendering_method": method,
            "output_file": output_file,
            "message": f"Visualization generated using {method}"
        })

    def _handle_document_rendering(self, params):
        """Handle document rendering."""
        doc_type = params.get("document_type")
        template = params.get("template", "professional")
        use_external = params.get("use_external_api", False)
        
        method = "external_api" if use_external and any(self.external_apis_enabled.values()) else "internal"
        output_file = f"document_{doc_type}.pdf" if "pdf" in doc_type else f"document_{doc_type}.html"
        
        return json.dumps({
            "status": "success",
            "document_type": doc_type,
            "template": template,
            "rendering_method": method,
            "output_file": output_file,
            "message": f"Document rendered using {method} method"
        })

    def _handle_file_operations(self, params):
        """Handle file I/O operations."""
        action = params.get("action")
        file_path = params.get("file_path", "")
        
        if action == "write":
            content = params.get("content", "")
            output_path = self.output_dir / file_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                with open(output_path, 'w') as f:
                    f.write(content)
                return json.dumps({
                    "status": "success",
                    "action": "write",
                    "file_path": str(output_path),
                    "bytes_written": len(content)
                })
            except Exception as e:
                return json.dumps({
                    "status": "error",
                    "message": str(e)
                })
        
        elif action == "read":
            try:
                with open(self.output_dir / file_path, 'r') as f:
                    content = f.read()
                return json.dumps({
                    "status": "success",
                    "action": "read",
                    "content": content
                })
            except Exception as e:
                return json.dumps({
                    "status": "error",
                    "message": str(e)
                })
        
        return json.dumps({"status": "simulated", "action": action})


if __name__ == "__main__":
    # Example usage
    system = AnalysisSystem()
    
    sample_data = """
    Sales Data Q4 2025:
    - Revenue: $1.2M (up 15% from Q3)
    - New customers: 450
    - Customer retention: 92%
    - Top product: Widget Pro (35% of sales)
    - Region performance: North America +20%, Europe +10%, Asia +8%
    """
    
    specs = {
        "format": "pdf_report",
        "type": "professional",
        "analysis": "summarize",
        "options": {
            "include_charts": True,
            "style": "professional",
            "length": "detailed"
        }
    }
    
    result = system.run_mission(sample_data, specs)
    print("\n" + "="*80)
    print("FINAL OUTPUT:")
    print("="*80)
    print(result)
