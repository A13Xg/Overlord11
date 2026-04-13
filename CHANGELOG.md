# Overlord11 Changelog

## [Unreleased]

### Fixed
- **Workspace Generation**: Fixed issue where multiple spurious workspace folders were created with job IDs. Now creates only ONE workspace folder per job with proper naming convention `{ISO_DATE}_{JOB_ID}`.
- **Folder Structure**: Implemented proper workspace hierarchy:
  - `workspace/{ISO_DATE}_{JOB_ID}/` — single root per job
  - `output/` — main deliverables (applications, reports, code)
  - `artifacts/` — supporting files (MD docs, logs, tool results)
  - Root MD files — ProjectOverview.md, Settings.md, TaskingLog.md, AInotes.md, ErrorLog.md
- **Artifact API**: Fixed artifacts.py to prevent fallback creation of `workspace/{job_id}` folders. Now requires session_id to be set before artifact access.
- **Publisher Tool**: Updated to save HTML outputs to `output/` folder by default instead of workspace root.

### Changed
- **task_workspace.py**: 
  - Updated `task_dir_for()` to accept job_id parameter for proper naming
  - Added `output/` folder to layout structure
  - Updated docstring to reflect new `{ISO_DATE}_{JOB_ID}` naming convention
- **session_manager.py (tools/python)**:
  - `create_session()` now accepts `job_id` parameter
  - Workspace naming changed to `{ISO_DATE}_{JOB_ID}` when job_id provided
  - Collision handling updated for suffix naming (`_v01`, `_v02`, etc.)
  - Added `--job_id` CLI parameter
- **engine_bridge.py**:
  - Updated `EngineRunner.run()` call to pass job_id from job object
- **runner.py**:
  - Added `job_id` parameter to `run()` method
  - Updated docstring to document job_id usage for workspace naming
- **EngineSession (session_manager.py - engine/)**:
  - Added `job_id` parameter to __init__
  - Updated `create()` to pass job_id to session creation
  - Updated docstring to explain workspace naming convention
- **artifacts.py**:
  - Removed fallback folder creation with job_id
  - Now raises 409 error if job lacks session_id instead of creating spurious folders
  - Updated error message to prompt job completion wait
- **publisher_tool.py**:
  - Changed default output path to `task_dir/output/` instead of `task_dir/`
- **publisher.md (agent)**:
  - Updated to specify saving to `output/` folder
  - Changed example path to show `output/` folder in workspace structure
- **reviewer.md (agent)**:
  - Added step to verify deliverables are in `output/` folder
  - Added workspace structure validation to quality checklist
  - Added output folder contents verification to responsibilities
- **session_manager.json (tool def)**:
  - Added `job_id` parameter documentation
  - Updated workspace naming description to reflect `{ISO_DATE}_{JOB_ID}` format

### Technical Details

#### Workspace Naming Convention
- **Single job, no webui job_id**: `workspace/20260413_000521/`
- **Single job with webui job_id**: `workspace/20260413_000521_9fcc067f/` (ISO date + job_id)
- **Collision handling**: `workspace/20260413_000521_9fcc067f_v01/` (adds version suffix)

#### Artifact API Behavior
- Artifacts can only be accessed if job has a valid `session_id` set
- `session_id` is set by EngineRunner after job completes
- Prevents spurious folder creation and ensures clean artifact organization

#### Output Tier System
- **Tier 0**: Direct text response (no file)
- **Tier 1**: Markdown file saved to `output/{name}.md`
- **Tier 2**: Styled HTML report saved to `output/{name}.html`

All tier outputs go to the `output/` folder within the workspace.

### Migration Notes
- Existing workspaces created before this change may have spurious job_id folders that can be safely deleted
- Empty directories like `workspace/{job_id}/` (without ISO prefix) should be cleaned up
- Sessions created with old format will still be accessible; new sessions use new format

