import os


def install_local_mail(api):
    # Never configure a capture mailbox for a production tenant or overwrite real SMTP.
    if (
        os.getenv("HRMS_LOCAL_MAIL_CAPTURE") != "true"
        or api.org != "11111111-1111-1111-1111-111111111111"
        or os.getenv("PLATFORM_API_URL") != "http://platform-api:8000/v1/api"
    ):
        return
    from .errors import AppError

    try:
        current = api.call("GET", f"/integrations/organizations/{api.org}/smtp")
        if current.get("config", {}).get("smtp_host") not in (None, "", "local-mail"):
            raise RuntimeError(
                "Local tenant has external SMTP configured; refusing to replace it automatically"
            )
    except AppError as exc:
        if exc.status != 404:
            raise
    api.call(
        "PUT",
        f"/integrations/organizations/{api.org}/smtp",
        json={
            "display_name": "Local test inbox (no external delivery)",
            "validate": False,
            "set_default": True,
            "config": {
                "smtp_host": "local-mail",
                "smtp_port": 1025,
                "from_email": "myhub@newtuple.com",
                "smtp_use_tls": False,
            },
            "secrets": {"username": "local", "password": "local"},
        },
    )
