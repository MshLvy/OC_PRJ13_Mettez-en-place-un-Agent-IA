"""Orchestration explicite ; aucune option d'outil active par défaut."""

from typing import Literal
from app.workflow_dispatch import dispatch

from fastapi import APIRouter, HTTPException, Request
from pydantic import ConfigDict, Field, StrictBool, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.config import ExplorerMode
from app.analysis_preferences import PreferenceError

from app.orchestration import AnalysisResponse, OrchestrationError
from app.position_routes import PositionRequest
from app.positions import FenValidationError

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


class AnalysisRequest(PositionRequest):
    model_config = ConfigDict(extra="forbid")
    engine_policy: Literal["requested", "theory_fallback"] = "requested"
    # None interne = absence. Null explicite interdit, absent du schéma public.
    explorer_mode: ExplorerMode | SkipJsonSchema[None] = Field(default=None, json_schema_extra=lambda s: s.pop("default", None))
    include_explorer: StrictBool | SkipJsonSchema[None] = Field(default=None, json_schema_extra=lambda s: s.pop("default", None))
    include_engine: StrictBool | SkipJsonSchema[None] = Field(default=None, json_schema_extra=lambda s: s.pop("default", None))

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null(cls, values):
        if isinstance(values, dict) and any(key in values and values[key] is None
                for key in ("explorer_mode", "include_explorer", "include_engine")):
            raise ValueError("NULL_ANALYSIS_PREFERENCE")
        return values


@router.post("/orchestrate", response_model=AnalysisResponse)
def orchestrate(body: AnalysisRequest, request: Request):
    try:
        return dispatch(request, 'analysis', body=body)
    except FenValidationError as error:
        raise HTTPException(422, detail={"code": error.code, "issues": list(error.issues)}) from None
    except PreferenceError as error:
        raise HTTPException(422, detail={"code": error.code}) from None
    except OrchestrationError as error:
        raise HTTPException(error.http_status, detail={"code": error.code}) from None
