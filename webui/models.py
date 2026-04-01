from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum

VALID_PROVIDERS = ["gemini", "openai", "anthropic"]


class JobStatus(str, Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
    pending = "pending"


class ArtifactInfo(BaseModel):
    path: str
    size: int
    mtime: float
    is_finished_product: bool = False


class JobSummary(BaseModel):
    job_id: str
    goal: Optional[str] = None
    status: JobStatus = JobStatus.pending
    created: Optional[float] = None
    updated: Optional[float] = None
    verify_summary: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class JobDetail(JobSummary):
    state: Optional[Dict[str, Any]] = None
    events: List[Dict[str, Any]] = []
    artifacts: List[ArtifactInfo] = []


class CreateJobRequest(BaseModel):
    goal: str
    provider: Optional[str] = None
    model: Optional[str] = None
    verify_command: Optional[str] = None


class SelectionRequest(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None


class ConfigInfo(BaseModel):
    active_provider: str
    providers: Dict[str, Any]
    default_model: str

