# Code-ProjectGen Setup and Troubleshooting Guide

## Quick Setup

### 1. Install Dependencies

```bash
cd Code-ProjectGen/python
pip install -r requirements.txt
```

### 2. Configure API Keys

**IMPORTANT**: You must set up your API key before running the application.

1. Copy the example environment file:
   ```bash
   cd ..
   cp .env.example .env
   ```

2. Edit `.env` and add your API key:
   ```bash
   # For Anthropic (default provider)
   ANTHROPIC_API_KEY=sk-ant-your-actual-api-key-here

   # OR for Gemini (if using gemini provider)
   GOOGLE_GEMINI_API_KEY=your-gemini-api-key-here
   ```

3. Get your API keys:
   - **Anthropic**: https://console.anthropic.com/settings/keys
   - **Gemini**: https://makersuite.google.com/app/apikey

### 3. Verify Setup

Run the test suite to verify everything is configured correctly:

```bash
cd python
pytest test_run.py -v
```

### 4. Run the Application

```bash
# Interactive mode (recommended for first-time users)
python run.py -i

# Quick test with default settings
python run.py --description "Create a simple calculator CLI" --use-sandbox --no-confirm
```

---

## Common Issues and Solutions

### Issue 1: "Could not resolve authentication method" Error

**Error Message:**
```
TypeError: "Could not resolve authentication method. Expected either api_key or auth_token to be set..."
```

**Root Cause:** The `ANTHROPIC_API_KEY` environment variable is not set.

**Solution:**

1. Ensure `.env` file exists in the project root:
   ```bash
   ls C:\Users\local.adm\Documents\GitHub\Overlord11\.env
   ```

2. If missing, create it from the example:
   ```bash
   copy .env.example .env
   ```

3. Edit `.env` and add your actual API key:
   ```
   ANTHROPIC_API_KEY=sk-ant-api03-YOUR_ACTUAL_KEY_HERE
   ```

4. Verify the key is loaded:
   ```python
   python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('Key loaded:', 'ANTHROPIC_API_KEY' in os.environ)"
   ```

---

### Issue 2: Import Errors

**Error Message:**
```
ModuleNotFoundError: No module named 'anthropic'
```

**Solution:**
```bash
cd Code-ProjectGen/python
pip install -r requirements.txt
```

---

### Issue 3: File Permission Errors

**Error Message:**
```
PermissionError: [Errno 13] Permission denied: 'workspace'
```

**Solution:**

1. Run as administrator (Windows):
   ```bash
   # Right-click Command Prompt/PowerShell -> Run as Administrator
   ```

2. Or use a different workspace:
   ```bash
   python run.py --workspace "C:\Users\YourName\Documents\projects" -i
   ```

---

### Issue 4: Configuration File Not Found

**Error Message:**
```
FileNotFoundError: config.json not found
```

**Solution:**

Ensure you're running the script from the correct directory:
```bash
cd C:\Users\local.adm\Documents\GitHub\Overlord11\Code-ProjectGen\python
python run.py -i
```

---

## Logging and Debugging

### Enable Debug Logging

Edit `python/run.py` line 15 to change logging level:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO to DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('code_projectgen.log', encoding='utf-8')
    ]
)
```

### View Logs

The application logs to two places:

1. **Console output** - real-time logging
2. **Log file** - `code_projectgen.log` in the `python/` directory

View the log file:
```bash
# Windows
type python\code_projectgen.log

# Unix/Linux/Mac
cat python/code_projectgen.log
```

---

## Testing

### Run All Tests

```bash
cd python
pytest test_run.py -v
```

### Run Specific Test

```bash
pytest test_run.py::TestGetModelClient::test_anthropic_client_missing_api_key -v
```

### Run with Coverage

```bash
pip install pytest-cov
pytest test_run.py --cov=run --cov-report=html
```

View coverage report: Open `htmlcov/index.html` in your browser

---

## Switching Between AI Providers

### Use Anthropic Claude (default)

Edit `config.json` line 5:
```json
"provider": "anthropic"
```

Set environment variable:
```bash
ANTHROPIC_API_KEY=sk-ant-your-key
```

### Use Google Gemini

Edit `config.json` line 5:
```json
"provider": "gemini"
```

Set environment variable:
```bash
GOOGLE_GEMINI_API_KEY=your-gemini-key
```

---

## Project Structure

```
Code-ProjectGen/
├── .env                    # API keys (YOU MUST CREATE THIS)
├── .env.example           # Template for .env file
├── config.json            # System configuration
├── agents/                # Agent role definitions
│   ├── orchestrator.md
│   ├── architect.md
│   ├── coder.md
│   ├── tester.md
│   └── reviewer.md
├── tools/                 # Tool definitions
│   ├── file_management.json
│   ├── code_execution.json
│   ├── project_scaffold.json
│   ├── code_analysis.json
│   └── dependency_management.json
├── python/
│   ├── run.py            # Main application
│   ├── test_run.py       # Unit tests
│   ├── requirements.txt   # Python dependencies
│   └── code_projectgen.log # Application log
├── workspace/            # Generated projects (default)
│   └── session_*/        # Session-specific workspaces
└── output/               # Session summaries
    └── session_*_summary.json
```

---

## Advanced Usage

### Custom Workspace

Generate code directly in your project directory:

```bash
python run.py \
  --workspace "C:\projects\my-new-app" \
  --description "Create a FastAPI REST API" \
  --template python_api \
  --no-confirm
```

### Batch Mode (No Interaction)

```bash
python run.py \
  --description "Create a CLI calculator" \
  --language python \
  --template python_cli \
  --features "Add operation" "Subtract operation" "Multiply" \
  --use-sandbox \
  --no-confirm
```

### Multiple Features

```bash
python run.py \
  --description "Build a user management API" \
  --template python_api \
  --features "User registration" "Login" "Password reset" "Email verification" \
  --include-docker \
  --interactive
```

---

## Troubleshooting Checklist

Before reporting issues, verify:

- [ ] `.env` file exists in `C:\Users\local.adm\Documents\GitHub\Overlord11\`
- [ ] API key is set correctly in `.env` (no quotes, no extra spaces)
- [ ] Dependencies are installed: `pip list | findstr anthropic`
- [ ] Running from correct directory: `python/` folder
- [ ] Configuration file exists: `config.json` in parent directory
- [ ] Check logs: `type python\code_projectgen.log`
- [ ] Python version: 3.8 or higher (`python --version`)

---

## Getting Help

1. **Check logs**: Review `code_projectgen.log` for detailed error messages
2. **Run tests**: Execute `pytest test_run.py -v` to identify issues
3. **Enable debug mode**: Set `level=logging.DEBUG` in run.py
4. **Verify environment**: Run the verification script below

### Environment Verification Script

Create `verify_setup.py` in the `python/` directory:

```python
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

print("=== Code-ProjectGen Setup Verification ===\n")

# Check Python version
print(f"1. Python Version: {sys.version}")
print(f"   Required: 3.8+")
print(f"   Status: {'✓ OK' if sys.version_info >= (3, 8) else '✗ FAIL'}\n")

# Check .env file
env_path = Path(__file__).parent.parent.parent / ".env"
print(f"2. .env File: {env_path}")
print(f"   Exists: {'✓ YES' if env_path.exists() else '✗ NO'}\n")

# Load and check API key
load_dotenv(env_path)
api_key = os.getenv('ANTHROPIC_API_KEY')
print(f"3. ANTHROPIC_API_KEY:")
print(f"   Set: {'✓ YES' if api_key else '✗ NO'}")
if api_key:
    print(f"   Length: {len(api_key)} characters")
    print(f"   Starts with: {api_key[:10]}...")
print()

# Check dependencies
print("4. Dependencies:")
try:
    import anthropic
    print("   anthropic: ✓ Installed")
except ImportError:
    print("   anthropic: ✗ Not installed")

try:
    import google.generativeai
    print("   google-generativeai: ✓ Installed")
except ImportError:
    print("   google-generativeai: ✗ Not installed")

try:
    from dotenv import load_dotenv
    print("   python-dotenv: ✓ Installed")
except ImportError:
    print("   python-dotenv: ✗ Not installed")

print("\n=== Verification Complete ===")
```

Run it:
```bash
python verify_setup.py
```

---

## Support

For issues not covered here:
1. Review the application logs
2. Run the verification script
3. Check that all dependencies are up to date
4. Ensure your API key has sufficient credits/permissions
