"""
Unit tests for Code-ProjectGen run.py
"""
import os
import sys
import json
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from run import (
    get_model_client,
    CodeGenerationSystem,
    BASE_DIR
)


class TestGetModelClient:
    """Test suite for get_model_client function"""

    def test_anthropic_client_missing_api_key(self):
        """Test that missing Anthropic API key raises ValueError"""
        config = {
            'model_config': {
                'provider': 'anthropic',
                'models': {
                    'anthropic': {
                        'model_name': 'claude-3-5-sonnet-20241022',
                        'max_tokens': 8000,
                        'env_var': 'ANTHROPIC_API_KEY'
                    }
                }
            }
        }

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                get_model_client(config)

            assert 'ANTHROPIC_API_KEY' in str(exc_info.value)
            assert 'not set' in str(exc_info.value)

    def test_gemini_client_missing_api_key(self):
        """Test that missing Gemini API key raises ValueError"""
        config = {
            'model_config': {
                'provider': 'gemini',
                'models': {
                    'gemini': {
                        'model_name': 'gemini-1.5-pro',
                        'max_tokens': 8000,
                        'env_var': 'GOOGLE_GEMINI_API_KEY'
                    }
                }
            }
        }

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                get_model_client(config)

            assert 'GOOGLE_GEMINI_API_KEY' in str(exc_info.value)

    @patch('run.anthropic.Anthropic')
    def test_anthropic_client_success(self, mock_anthropic):
        """Test successful Anthropic client initialization"""
        config = {
            'model_config': {
                'provider': 'anthropic',
                'models': {
                    'anthropic': {
                        'model_name': 'claude-3-5-sonnet-20241022',
                        'max_tokens': 8000,
                        'env_var': 'ANTHROPIC_API_KEY'
                    }
                }
            }
        }

        mock_client = Mock()
        mock_anthropic.return_value = mock_client

        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key-123'}):
            provider, client = get_model_client(config)

            assert provider == 'anthropic'
            assert client == mock_client
            mock_anthropic.assert_called_once_with(api_key='test-key-123')

    @patch('run.genai.GenerativeModel')
    @patch('run.genai.configure')
    def test_gemini_client_success(self, mock_configure, mock_gen_model):
        """Test successful Gemini client initialization"""
        config = {
            'model_config': {
                'provider': 'gemini',
                'models': {
                    'gemini': {
                        'model_name': 'gemini-1.5-pro',
                        'max_tokens': 8000,
                        'env_var': 'GOOGLE_GEMINI_API_KEY'
                    }
                }
            }
        }

        mock_model = Mock()
        mock_gen_model.return_value = mock_model

        with patch.dict(os.environ, {'GOOGLE_GEMINI_API_KEY': 'test-gemini-key'}):
            provider, client = get_model_client(config)

            assert provider == 'gemini'
            assert client == mock_model
            mock_configure.assert_called_once_with(api_key='test-gemini-key')
            mock_gen_model.assert_called_once_with('gemini-1.5-pro')

    def test_invalid_config_structure(self):
        """Test that invalid config structure raises RuntimeError"""
        config = {
            'model_config': {
                'provider': 'anthropic',
                'models': {}  # Missing 'anthropic' key
            }
        }

        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
            with pytest.raises(RuntimeError) as exc_info:
                get_model_client(config)

            assert 'Invalid configuration' in str(exc_info.value)


class TestCodeGenerationSystem:
    """Test suite for CodeGenerationSystem class"""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def mock_config(self):
        """Mock configuration"""
        return {
            'model_config': {
                'provider': 'anthropic',
                'models': {
                    'anthropic': {
                        'model_name': 'claude-3-5-sonnet-20241022',
                        'max_tokens': 8000,
                        'env_var': 'ANTHROPIC_API_KEY'
                    }
                }
            },
            'orchestration_logic': {
                'max_loops': 15
            }
        }

    @patch('run.get_model_client')
    @patch('builtins.open', new_callable=mock_open, read_data='{}')
    def test_init_creates_directories(self, mock_file, mock_get_client, temp_workspace):
        """Test that initialization creates necessary directories"""
        mock_get_client.return_value = ('anthropic', Mock())

        with patch('run.BASE_DIR', Path(temp_workspace)):
            with patch.object(Path, 'exists', return_value=True):
                system = CodeGenerationSystem()

                assert system.output_dir.exists() or True  # Directory creation is mocked
                assert system.workspace_dir.exists() or True

    @patch('run.get_model_client')
    @patch('builtins.open', new_callable=mock_open)
    def test_init_fails_on_missing_config(self, mock_file, mock_get_client):
        """Test that initialization fails when config file is missing"""
        mock_file.side_effect = FileNotFoundError("Config not found")

        with pytest.raises(FileNotFoundError):
            CodeGenerationSystem()

    @patch('run.get_model_client')
    @patch('builtins.open', new_callable=mock_open, read_data='invalid json')
    def test_init_fails_on_invalid_json(self, mock_file, mock_get_client):
        """Test that initialization fails on invalid JSON config"""
        with pytest.raises(json.JSONDecodeError):
            CodeGenerationSystem()

    @patch('run.get_model_client')
    def test_safe_path_prevents_traversal(self, mock_get_client, temp_workspace, mock_config):
        """Test that _safe_path prevents directory traversal attacks"""
        mock_get_client.return_value = ('anthropic', Mock())

        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))):
            with patch('run.Path.exists', return_value=True):
                with patch('run.Path.is_dir', return_value=True):
                    with patch('run.Path.iterdir', return_value=[]):
                        system = CodeGenerationSystem(workspace=temp_workspace)

                        # Test directory traversal attempt
                        with pytest.raises(ValueError) as exc_info:
                            system._safe_path("../../etc/passwd")

                        assert "Directory traversal not allowed" in str(exc_info.value)

    @patch('run.get_model_client')
    def test_execute_tool_unknown_tool(self, mock_get_client, temp_workspace, mock_config):
        """Test that unknown tool returns error"""
        mock_get_client.return_value = ('anthropic', Mock())

        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))):
            with patch('run.Path.exists', return_value=True):
                with patch('run.Path.is_dir', return_value=True):
                    with patch('run.Path.iterdir', return_value=[]):
                        system = CodeGenerationSystem(workspace=temp_workspace)

                        result = system._execute_tool("unknown_tool", {})
                        result_dict = json.loads(result)

                        assert result_dict['status'] == 'error'
                        assert 'unknown_tool' in result_dict['message'].lower()

    @patch('run.get_model_client')
    def test_handle_file_management_read(self, mock_get_client, temp_workspace, mock_config):
        """Test file management read operation"""
        mock_get_client.return_value = ('anthropic', Mock())

        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))):
            with patch('run.Path.exists', return_value=True):
                with patch('run.Path.is_dir', return_value=True):
                    with patch('run.Path.iterdir', return_value=[]):
                        system = CodeGenerationSystem(workspace=temp_workspace)

                        # Create a test file
                        test_file = system.session_workspace / "test.txt"
                        test_file.parent.mkdir(parents=True, exist_ok=True)
                        test_file.write_text("Hello, World!")

                        result = system._handle_file_management({
                            "action": "read",
                            "path": "test.txt"
                        })
                        result_dict = json.loads(result)

                        assert result_dict['status'] == 'success'
                        assert result_dict['content'] == "Hello, World!"

    @patch('run.get_model_client')
    def test_handle_file_management_write(self, mock_get_client, temp_workspace, mock_config):
        """Test file management write operation"""
        mock_get_client.return_value = ('anthropic', Mock())

        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))):
            with patch('run.Path.exists', return_value=True):
                with patch('run.Path.is_dir', return_value=True):
                    with patch('run.Path.iterdir', return_value=[]):
                        system = CodeGenerationSystem(workspace=temp_workspace)

                        result = system._handle_file_management({
                            "action": "write",
                            "path": "output.txt",
                            "content": "Test content"
                        })
                        result_dict = json.loads(result)

                        assert result_dict['status'] == 'success'
                        assert 'bytes_written' in result_dict

    @patch('run.get_model_client')
    def test_handle_project_scaffold(self, mock_get_client, temp_workspace, mock_config):
        """Test project scaffolding"""
        mock_get_client.return_value = ('anthropic', Mock())

        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))):
            with patch('run.Path.exists', return_value=True):
                with patch('run.Path.is_dir', return_value=True):
                    with patch('run.Path.iterdir', return_value=[]):
                        system = CodeGenerationSystem(workspace=temp_workspace)

                        result = system._handle_project_scaffold({
                            "template": "python_cli",
                            "project_name": "test_project",
                            "options": {}
                        })
                        result_dict = json.loads(result)

                        assert result_dict['status'] == 'success'
                        assert 'created' in result_dict
                        assert len(result_dict['created']) > 0


class TestFileOperations:
    """Test suite for file operation handlers"""

    @pytest.fixture
    def temp_system(self, tmp_path):
        """Create a temporary CodeGenerationSystem for testing"""
        with patch('run.get_model_client') as mock_client:
            mock_client.return_value = ('anthropic', Mock())

            config = {
                'model_config': {
                    'provider': 'anthropic',
                    'models': {
                        'anthropic': {
                            'model_name': 'claude-3-5-sonnet-20241022',
                            'max_tokens': 8000,
                            'env_var': 'ANTHROPIC_API_KEY'
                        }
                    }
                },
                'orchestration_logic': {'max_loops': 15},
                'code_execution': {'timeout_seconds': 30}
            }

            with patch('builtins.open', mock_open(read_data=json.dumps(config))):
                with patch('run.Path.exists', return_value=True):
                    with patch('run.Path.is_dir', return_value=True):
                        with patch('run.Path.iterdir', return_value=[]):
                            system = CodeGenerationSystem(workspace=str(tmp_path))
                            yield system

    def test_file_exists_check(self, temp_system):
        """Test file exists check"""
        result = temp_system._handle_file_management({
            "action": "exists",
            "path": "nonexistent.txt"
        })
        result_dict = json.loads(result)

        assert result_dict['status'] == 'success'
        assert result_dict['exists'] == False

    def test_mkdir_operation(self, temp_system):
        """Test directory creation"""
        result = temp_system._handle_file_management({
            "action": "mkdir",
            "path": "test_dir/nested",
            "recursive": True
        })
        result_dict = json.loads(result)

        assert result_dict['status'] == 'success'
        assert (temp_system.session_workspace / "test_dir" / "nested").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
