# Only put reusable functions here

import mimetypes
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any, NoReturn

import argon2
from dotenv import find_dotenv, load_dotenv
from fastapi import HTTPException, status
from passlib.context import CryptContext

from common.configuration import get_configuration
from common.logger import logger
from exceptions import (
    AuthorizationError,
    ConflictError,
    DBException,
    NotFoundError,
    PersistenceError,
    RecordNotFoundException,
    ServiceError,
    ValidationError,
)

_ = load_dotenv(find_dotenv())


def send_alert(
    message="Message to send",
    subject="Alert",
    file_to_send=None,
    filename="alert_log.txt",
    mail_to="",
    mail_cc="",
):
    """Send an email alert with an attachment if any

    Args:
        message (str): Message to be sent via email
        subject (str): Subject of the email. Defaults to Alert
        file_to_send (str, optional): Path to file to send via email attachment. Defaults to None.
        filename (str, optional): File name of the attachment. Defaults to 'alert_log.txt'.
        mail_to (str, optional): Recipient of the email. Defaults to ""
        mail_cc (str, optional): CC of the email. Defaults to ""
    """

    SMTP_HOST = get_configuration().smtp_configuration.host
    SMTP_TLS_PORT = get_configuration().smtp_configuration.port
    SMTP_MAIL_FROM = get_configuration().smtp_configuration.from_email
    SMTP_MAIL_TO = get_configuration().smtp_configuration.mail_to
    SMTP_PASSWORD = get_configuration().smtp_configuration.password
    SMTP_USER = get_configuration().smtp_configuration.username
    SMTP_DISPLAY_NAME = get_configuration().smtp_configuration.from_name

    msg = MIMEMultipart()

    msg["Subject"] = subject
    msg["From"] = SMTP_MAIL_FROM
    msg["From"] = formataddr((SMTP_DISPLAY_NAME, SMTP_MAIL_FROM))

    if mail_to:
        SMTP_MAIL_TO = mail_to
    if mail_cc:
        msg["Cc"] = mail_cc

    # msg['To'] requires SMTP_MAIL_TO to be a string
    msg["To"] = SMTP_MAIL_TO
    msg.attach(MIMEText(message, "html"))

    if file_to_send:
        ctype, encoding = mimetypes.guess_type(file_to_send)
        if ctype is None or encoding is not None:
            ctype = "text/*"

        _maintype, _subtype = ctype.split("/", 1)

        if "xlsx" not in file_to_send:
            with open(file_to_send, encoding="utf-8") as fp:
                attachment = MIMEText(fp.read(), _subtype="subtype")
                # encoders.encode_base64(attachment)
                attachment.add_header("Content-Disposition", "attachment", filename=filename)
                msg.attach(attachment)
        else:
            with open(file_to_send, "rb") as fp:
                # attachment = MIMEText(fp.read(), _subtype='xlsx')
                attachment = MIMEBase("application", "octet-stream")
                attachment.set_payload(fp.read())
                encoders.encode_base64(attachment)
                attachment.add_header(
                    "Content-Disposition", "attachment", filename=f"{filename}.xlsx"
                )
                msg.attach(attachment)

    with smtplib.SMTP(SMTP_HOST, SMTP_TLS_PORT) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(SMTP_USER, SMTP_PASSWORD)

        # sendmail requires SMTP_MAIL_TO to be a list
        smtp.sendmail(SMTP_MAIL_FROM, SMTP_MAIL_TO.split(","), msg.as_string())


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


ph = argon2.PasswordHasher()


def get_password_hash(password: str):
    """Get hashed password

    Args:
        password (str): password to hash
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str):
    """Verify password

    Args:
        plain_password (str): plain password
        hashed_password (str): hashed password
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash_using_argon(password: str):
    """Get hashed password

    Args:
        password (str): password to hash
    """
    return ph.hash(password)


def verify_password_using_argon(plain_password: str, hashed_password: str):
    """Verify password

    Args:
        plain_password (str): plain password
        hashed_password (str): hashed password
    """
    return ph.verify(hashed_password, plain_password)


def custom_key_builder(fn: Any, *args: tuple[Any], **kwargs: dict[str, Any]) -> str:
    """Custom key builder for cache entries.

    Args:
        fn: The function being cached
        args: Positional arguments
        kwargs: Keyword arguments

    Returns:
        Formatted cache key as string
    """
    fname = fn.__name__

    # Filter out non-cacheable arguments
    filtered_kwargs = {}
    for k, v in kwargs.items():
        # Skip Request objects and other non-serializable objects
        if k in ["request"]:
            continue
        # Convert complex objects to string representation
        try:
            if hasattr(v, "__dict__"):
                # For objects like ListFilesRequest, User, etc.
                if hasattr(v, "id"):
                    filtered_kwargs[k] = f"{type(v).__name__}_{v.id}"
                else:
                    # Convert object attributes to a stable string
                    attrs = {
                        attr: getattr(v, attr)
                        for attr in dir(v)
                        if not attr.startswith("_") and not callable(getattr(v, attr))
                    }
                    filtered_kwargs[k] = f"{type(v).__name__}_{hash(str(sorted(attrs.items())))}"
            else:
                filtered_kwargs[k] = str(v)
        except Exception:
            # Fallback for problematic objects
            filtered_kwargs[k] = f"{type(v).__name__}"

    # Format args/kwargs into string
    args_str = ":".join(str(arg) for arg in args if arg is not None)
    kwargs_str = ":".join(f"{k}={v}" for k, v in filtered_kwargs.items())

    # Build key with components
    key_parts = [fname]
    if args_str:
        key_parts.append(args_str)
    if kwargs_str:
        key_parts.append(kwargs_str)

    cache_key = ":".join(key_parts)
    return cache_key


def ensure_non_empty(value: str, field_name: str) -> str:
    """Strip and validate that a string is non-empty. Raise ValueError otherwise."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _exc_detail(exc: Exception) -> str:
    """Prefer `exc.detail` when set (ModularError), fall back to str(exc)."""
    detail = getattr(exc, "detail", None)
    return detail if isinstance(detail, str) and detail else str(exc)


def _custom_status(exc: Exception) -> int | None:
    """Return `exc.status_code` if it's a valid HTTP status int, else None.

    Domain code may attach a `status_code` attribute to a ModularError to
    override the default type-based mapping (e.g. ValidationError with 401
    instead of 400).
    """
    code = getattr(exc, "status_code", None)
    if isinstance(code, int) and 100 <= code < 600:
        return code
    return None


def raise_http_error(exc: Exception, context: dict[str, Any] | None = None) -> NoReturn:
    """Translate domain and persistence errors into HTTP exceptions and log with context."""
    log_context: dict[str, Any] = dict(context or {})
    log_context["exception_type"] = type(exc).__name__
    log_context["exception_message"] = str(exc)
    if isinstance(exc, HTTPException):
        log_context["http_status_code"] = exc.status_code
        logger.exception("HTTP exception raised in controller flow", extra=log_context)
        raise exc
    if isinstance(exc, (RecordNotFoundException, NotFoundError)):
        code = _custom_status(exc) or status.HTTP_404_NOT_FOUND
        logger.exception("Resource not found while handling request", extra=log_context)
        raise HTTPException(status_code=code, detail=_exc_detail(exc)) from exc
    if isinstance(exc, (ValidationError, ValueError)):
        code = _custom_status(exc) or status.HTTP_400_BAD_REQUEST
        logger.exception("Validation failed while handling request", extra=log_context)
        raise HTTPException(status_code=code, detail=_exc_detail(exc)) from exc
    if isinstance(exc, (AuthorizationError, PermissionError)):
        code = _custom_status(exc) or status.HTTP_403_FORBIDDEN
        logger.exception("Authorization failed while handling request", extra=log_context)
        raise HTTPException(status_code=code, detail=_exc_detail(exc)) from exc
    if isinstance(exc, ConflictError):
        code = _custom_status(exc) or status.HTTP_409_CONFLICT
        logger.exception("Conflict detected while handling request", extra=log_context)
        raise HTTPException(status_code=code, detail=_exc_detail(exc)) from exc
    if isinstance(exc, (DBException, PersistenceError, ServiceError)):
        code = _custom_status(exc) or status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.exception("Persistence or service error while handling request", extra=log_context)
        raise HTTPException(status_code=code, detail=_exc_detail(exc)) from exc
    logger.exception("Unhandled exception while handling request", extra=log_context)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error"
    ) from exc
