# Gemini Toolset

A comprehensive collection of specialized agents and tools designed to empower a Large Language Model (LLM) for diverse software engineering tasks within a CLI environment.

## 🟦 Overview

The Gemini Toolset provides the LLM with a robust and standardized set of capabilities to interact with the file system, execute shell commands, perform calculations, manage Git repositories, and much more. This framework enables the LLM to understand its operational context and leverage specific tools and collaborate with specialized agents to achieve complex objectives efficiently and safely.

## 🛠️ Available Tools

The following tools are available to agents within the Gemini Toolset, facilitating various interactions with the environment:

*   **calculator_tool**: Performs basic arithmetic operations and advanced mathematical functions.
*   **delegate_to_agent**: Delegates a task to a specialized sub-agent.
*   **get_datetime**: Returns the current date and time.
*   **git_tool**: Executes specified Git commands.
*   **glob**: Efficiently finds files matching specific glob patterns.
*   **list_directory**: Lists contents of a specified directory.
*   **read_file**: Reads and returns content of a specified file, with pagination.
*   **replace**: Replaces text within a file.
*   **run_shell_command**: Executes arbitrary shell commands.
*   **save_memory**: Saves specific facts or information to long-term memory.
*   **search_file_content**: Performs fast, optimized content searches using `ripgrep`.
*   **web_fetch**: Performs basic HTTP GET requests and retrieves content from URLs.
*   **write_file**: Writes content to a specified file.

## 👤 Available Agents

The Gemini Toolset includes a diverse array of specialized agents, each designed to handle specific types of tasks and collaborate to achieve larger goals:

*   **Advanced Analyst Agent**: Analyzes data and presents it visually.
*   **API Tester Agent**: Tests and verifies web APIs.
*   **Automation Agent**: Creates and manages automation scripts and workflows.
*   **Auto Bug Fixing Agent**: Automatically detects, diagnoses, and fixes bugs.
*   **Code Debugger Agent**: Identifies and fixes bugs in code.
*   **Code Generator Agent**: Writes clean, efficient, and well-documented code.
*   **Code Reviewer Agent**: Ensures code quality, correctness, and maintainability.
*   **Code Tester Agent**: Validates code functionality by writing and executing tests.
*   **Command Executor Agent**: Executes shell commands in a safe, isolated environment.
*   **Config Manager Agent**: Manages and modifies configuration files.
*   **Data Visualizer Agent**: Creates various data visualizations, especially dynamic HTML outputs.
*   **Deployment Agent**: Automates the deployment of applications.
*   **Fact Checker Agent**: Verifies the accuracy of information.
*   **File Manager Agent**: Interacts with the file system for various operations.
*   **Git Agent**: Manages source code repositories with Git.
*   **HTML Visualization Agent**: Generates dynamic and well-styled HTML pages for data visualization.
*   **Human in the Loop Agent**: Asks for clarification when requirements are ambiguous or decisions are needed.
*   **Language Agent**: Understands and processes human language.
*   **Learning Agent**: Learns from user feedback to improve agent performance.
*   **Monitoring Agent**: Monitors the health and performance of applications.
*   **Orchestrator Agent**: Manages overall workflow and delegates tasks.
*   **Planner Agent**: Breaks down complex tasks into manageable steps and structures them for optimal execution.
*   **Proofreader Agent**: Improves the quality of written text.
*   **Researcher Agent**: Finds and synthesizes information from various sources.
*   **Summarizer Agent**: Creates concise summaries of long-form text.
*   **UI/UX Feedback Agent**: Provides feedback on user interface and experience.

## 🚀 Getting Started

To onboard a new LLM instance or to understand the operational context, refer to the `onboarding.md` file. This document details the environment, tool usage, and interaction guidelines for the LLM.

## 🗺️ Roadmap

For a detailed outline of future improvements and planned enhancements, please refer to the `Roadmap.md` file.
