import logging
from django.core.mail import send_mail
from decouple import config

logger = logging.getLogger(__name__)

# Note: Set EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD in your .env
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="alerts@arishem.com")

def send_drift_alert(workspace_name: str, drift_score: float, admin_emails: list[str]):
    """
    Sends an email alert when data drift is detected.
    """
    if not admin_emails:
        logger.warning(f"No admin emails provided for drift alert in workspace: {workspace_name}")
        return

    subject = f"⚠️ Arishem Alert: Data Drift Detected in Workspace '{workspace_name}'"
    message = (
        f"Hello,\n\n"
        f"Our monitoring system has detected data drift in your workspace '{workspace_name}'.\n"
        f"Drift Score (Avg Similarity Drop): {drift_score:.4f}\n\n"
        f"This indicates that recent queries are significantly different from the expected distribution or not well-represented in your vector database. You may want to ingest more relevant documents to improve RAG performance.\n\n"
        f"Best,\n"
        f"Arishem Monitoring Team"
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=DEFAULT_FROM_EMAIL,
            recipient_list=admin_emails,
            fail_silently=True,
        )
        logger.info(f"Drift alert email sent for workspace '{workspace_name}' to {admin_emails}")
    except Exception as e:
        logger.exception("Failed to send drift alert email.")


def send_error_alert(workspace_name: str, error_count: int, admin_emails: list[str]):
    """
    Sends an email alert when an unusual number of errors occurs.
    """
    if not admin_emails:
        return

    subject = f"🚨 Arishem Alert: High Error Rate in Workspace '{workspace_name}'"
    message = (
        f"Hello,\n\n"
        f"Our monitoring system has detected {error_count} recent errors during queries in your workspace '{workspace_name}'.\n"
        f"Please check the monitoring dashboard for more details.\n\n"
        f"Best,\n"
        f"Arishem Monitoring Team"
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=DEFAULT_FROM_EMAIL,
            recipient_list=admin_emails,
            fail_silently=True,
        )
        logger.info(f"Error alert email sent for workspace '{workspace_name}' to {admin_emails}")
    except Exception as e:
        logger.exception("Failed to send error alert email.")
