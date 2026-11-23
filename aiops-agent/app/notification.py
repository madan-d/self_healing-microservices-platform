import logging
import httpx
from typing import Optional
from .models import RootCauseAnalysisResult, RemediationActionEnum
from .config import settings

logger = logging.getLogger("aiops.notification")


class NotificationService:
    def __init__(
        self,
        slack_webhook_url: Optional[str] = settings.SLACK_WEBHOOK_URL,
        discord_webhook_url: Optional[str] = settings.DISCORD_WEBHOOK_URL,
        public_agent_url: str = settings.PUBLIC_AGENT_URL
    ):
        self.slack_webhook_url = slack_webhook_url
        self.discord_webhook_url = discord_webhook_url
        self.public_agent_url = public_agent_url.rstrip("/")

    async def notify_rca(self, rca: RootCauseAnalysisResult, auto_remediated: bool = False):
        """Dispatches formatted Root Cause Analysis to Slack or Discord."""
        if self.slack_webhook_url:
            await self._send_slack_block_kit(rca, auto_remediated)
        if self.discord_webhook_url:
            await self._send_discord_embed(rca, auto_remediated)

        # Always log high-visibility CLI summary
        banner = "🤖 [AIOps TRIAGE BOT ALERT]"
        logger.info(f"{banner} Resource: {rca.target_resource} | Severity: {rca.severity} | Category: {rca.category}")
        logger.info(f">> Summary: {rca.summary}")
        logger.info(f">> Recommended Action: {rca.recommended_action} (Auto-Remediated: {auto_remediated})")
        logger.info(f">> Exact Fix: {rca.exact_fix_instructions}")

    async def _send_slack_block_kit(self, rca: RootCauseAnalysisResult, auto_remediated: bool):
        """Builds rich Slack Block Kit layout with interactive approval buttons."""
        color = "#ef4444" if rca.severity == "CRITICAL" else "#f59e0b"
        status_badge = "✅ Safe Auto-Remediation Executed" if auto_remediated else "⚠️ Action Required (Human-in-the-Loop)"
        rollback_url = f"{self.public_agent_url}/actions/rollback?app={rca.target_resource}&namespace={rca.namespace}"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚨 AIOps Incident Triage: {rca.alert_name}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Resource:* `{rca.target_resource}`\n*Namespace:* `{rca.namespace}`"},
                    {"type": "mrkdwn", "text": f"*Severity:* `{rca.severity}`\n*Category:* `{rca.category}`"}
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{status_badge}*\n*Root Cause:* {rca.summary}\n\n*Detailed Analysis:*\n{rca.detailed_root_cause}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Recommended Fix:*\n```{rca.exact_fix_instructions}```"
                }
            }
        ]

        # If a rollback is recommended, provide a One-Click Action button
        if rca.recommended_action == RemediationActionEnum.APPROVE_ROLLBACK and not auto_remediated:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🚀 Approve Rollback (ArgoCD)", "emoji": True},
                        "style": "danger",
                        "url": rollback_url,
                        "value": "approve_rollback"
                    }
                ]
            })

        payload = {"blocks": blocks}
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(self.slack_webhook_url, json=payload)
                logger.info(f"Slack notification sent (status={res.status_code})")
        except Exception as exc:
            logger.error(f"Failed to post to Slack: {exc}")

    async def _send_discord_embed(self, rca: RootCauseAnalysisResult, auto_remediated: bool):
        """Builds Discord webhook embed."""
        embed = {
            "title": f"🚨 AIOps Incident: {rca.alert_name}",
            "color": 15548997 if rca.severity == "CRITICAL" else 16753920,
            "fields": [
                {"name": "Target", "value": f"`{rca.namespace}/{rca.target_resource}`", "inline": True},
                {"name": "Severity", "value": f"`{rca.severity}`", "inline": True},
                {"name": "Category", "value": f"`{rca.category}`", "inline": True},
                {"name": "Root Cause", "value": rca.summary, "inline": False},
                {"name": "Recommended Action", "value": f"`{rca.recommended_action}`", "inline": True},
                {"name": "Auto-Remediated", "value": "Yes" if auto_remediated else "No (Human approval)", "inline": True},
                {"name": "Exact Fix Instructions", "value": f"```{rca.exact_fix_instructions}```", "inline": False}
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                await client.post(self.discord_webhook_url, json={"embeds": [embed]})
        except Exception as exc:
            logger.error(f"Failed to post to Discord: {exc}")
