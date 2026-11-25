from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from enum import Enum


class AlertStatus(str, Enum):
    FIRING = "firing"
    RESOLVED = "resolved"


class AlertItem(BaseModel):
    status: AlertStatus
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)
    startsAt: Optional[str] = None
    endsAt: Optional[str] = None
    generatorURL: Optional[str] = None


class AlertmanagerPayload(BaseModel):
    version: Optional[str] = "4"
    groupKey: Optional[str] = None
    status: AlertStatus
    receiver: Optional[str] = None
    groupLabels: Dict[str, str] = Field(default_factory=dict)
    commonLabels: Dict[str, str] = Field(default_factory=dict)
    commonAnnotations: Dict[str, str] = Field(default_factory=dict)
    externalURL: Optional[str] = None
    alerts: List[AlertItem] = Field(default_factory=list)


class SeverityEnum(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CauseCategoryEnum(str, Enum):
    TRANSIENT_INFRA = "TRANSIENT_INFRA"          # e.g., brief network blip, hung process, transient lock
    CODE_EXCEPTION = "CODE_EXCEPTION"            # unhandled exception, syntax error, null pointer
    CONFIG_ERROR = "CONFIG_ERROR"                # missing env var, invalid db credentials
    OOM_MEMORY_LEAK = "OOM_MEMORY_LEAK"          # out of memory killed
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"    # database or external upstream down


class RemediationActionEnum(str, Enum):
    AUTO_RESTART = "AUTO_RESTART"
    APPROVE_ROLLBACK = "APPROVE_ROLLBACK"
    SCALE_UP = "SCALE_UP"
    MANUAL_INVESTIGATION = "MANUAL_INVESTIGATION"


class RootCauseAnalysisResult(BaseModel):
    alert_name: str
    target_resource: str
    namespace: str
    severity: SeverityEnum
    category: CauseCategoryEnum
    summary: str
    detailed_root_cause: str
    recommended_action: RemediationActionEnum
    exact_fix_instructions: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    evidence_logs: Optional[str] = None
    evidence_events: Optional[str] = None
    git_commit_info: Optional[str] = None


class RollbackRequest(BaseModel):
    application_name: str
    namespace: str
    target_revision: Optional[str] = None
    reason: str


class RemediationActionResponse(BaseModel):
    incident_id: str
    status: str
    action_taken: str
    message: str
    rca: RootCauseAnalysisResult
