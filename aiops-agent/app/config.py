from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Service settings
    APP_NAME: str = "aiops-incident-agent"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # LLM Settings
    LLM_PROVIDER: str = "auto"  # "bedrock", "openai", "auto", or "heuristic"
    AWS_REGION: str = "us-east-1"
    BEDROCK_MODEL_ID: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Notification Webhooks
    SLACK_WEBHOOK_URL: Optional[str] = None
    DISCORD_WEBHOOK_URL: Optional[str] = None
    PUBLIC_AGENT_URL: str = "http://localhost:8000"

    # GitOps (ArgoCD) Settings
    ARGOCD_SERVER: str = "http://argocd-server.argocd.svc.cluster.local"
    ARGOCD_AUTH_TOKEN: Optional[str] = None

    # Logging Aggregator (Loki)
    LOKI_URL: str = "http://loki.monitoring.svc.cluster.local:3100"

    # Auto-Remediation Safety Controls
    AUTO_REMEDIATION_ENABLED: bool = True
    MAX_AUTO_RESTARTS_PER_HOUR: int = 3

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
