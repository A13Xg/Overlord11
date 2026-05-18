from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict


class StrictParamsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass
class ToolContract:
    name: str
    params_model: type[StrictParamsModel]
    execute: Any

