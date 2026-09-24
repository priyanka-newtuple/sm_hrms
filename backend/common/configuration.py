"""Implements the default configuration.

`.env` is loaded eagerly at module import time so any subsequent code that reads
`os.environ` (including this module's own Configuration class) sees the loaded
values. The path resolves from the `ENV_FILE` env var, falling back to
`./etc/.env`. Override at runtime via `ENV_FILE=/path/to/.env`.
"""

import configparser
import json
import os
import socket
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE: str = os.environ.get("ENV_FILE", "./etc/.env")
load_dotenv(ENV_FILE)

from common.data_model import (  # noqa: E402
    DEFAULT_ACTION_RUNS_QUEUE,
)
from common.data_model import Configuration as ConfigurationModel  # noqa: E402

JWT_MIN_SECRET_LENGTH = 32
# Placeholder values shipped in env.example / backend/etc/.env.example — long
# enough to pass the length check, but public, so must be rejected explicitly.
JWT_FORBIDDEN_SECRET_VALUES = frozenset(
    {
        "your-secret-key-here-change-in-production",
        "change-this-to-a-strong-secret-in-production",
    }
)


class Configuration:
    """Represents the default configuration"""

    def __init__(self):
        """
        Initialize the configuration with default values.
        """
        self._config = configparser.ConfigParser()
        config_ini_path = os.environ.get("CONFIG_INI_PATH", "").strip()
        if config_ini_path:
            self._config.read(config_ini_path)

        config_obj = {
            "application_name": os.environ.get("APPLICATION_NAME", "fantanstic_app"),
            "environment": os.environ.get("ENVIRONMENT", "local"),
            "logger_configuration": {
                "log_level": os.environ.get("LOG_LEVEL", "DEBUG"),
                "enable_rich_logger": os.environ.get("ENABLE_RICH_LOGGER", 0),
                "enable_json_filelogger": os.environ.get("ENABLE_JSON_FILELOGGER", 0),
                "log_dir": os.environ.get("MODULAR_BACKEND_LOG_DIR", "logs"),
            },
            "server_configuration": {
                "host": os.environ.get("HOST", "0.0.0.0"),  # nosec
                "port": os.environ.get("PORT", "8081"),  # nosec
                "proxy_url": os.environ.get(
                    "PROXY_URL",
                    f"http://{os.environ.get('HOST', '0.0.0.0')}:{os.environ.get('PORT', '8081')}",
                ),  # nosec
                "request_timeout_seconds": int(os.environ.get("REQUEST_TIMEOUT_SECONDS", 60)),
            },
            "runtime_configuration": {
                "sql_echo": os.environ.get("SQL_ECHO", "false").lower() == "true",
                "encryption_key": os.environ.get("ENCRYPTION_KEY")
                or os.environ.get("JWT_SECRET_KEY", ""),
                "frontend_url": os.environ.get("FRONTEND_URL", "http://localhost:5173"),
                "litellm_model": os.environ.get("LITELLM_MODEL", ""),
                "litellm_api_base": os.environ.get("LITELLM_API_BASE", ""),
                "inbound_email_domain": os.environ.get("INBOUND_EMAIL_DOMAIN", "ats.newtuple.com"),
                "inbound_email_webhook_secret": os.environ.get("INBOUND_EMAIL_WEBHOOK_SECRET", ""),
                "inbound_email_allowed_bucket": os.environ.get("INBOUND_EMAIL_ALLOWED_BUCKET", ""),
                "inbound_email_s3_region": os.environ.get("INBOUND_EMAIL_S3_REGION", ""),
                "inbound_email_s3_access_key_id": os.environ.get(
                    "INBOUND_EMAIL_S3_ACCESS_KEY_ID", ""
                ),
                "inbound_email_s3_secret_access_key": os.environ.get(
                    "INBOUND_EMAIL_S3_SECRET_ACCESS_KEY", ""
                ),
            },
            "openai_configuration": {
                "api_key": os.environ.get("OPENAI_API_KEY", "SAMPLE_OPENAI_API_KEY"),
                "model_name": os.environ.get("OPENAI_MODEL_NAME", "SAMPLE_OPENAI_MODEL_NAME"),
                "guardrail_model_name": os.environ.get(
                    "OPENAI_GUARDRAIL_MODEL_NAME", "SAMPLE_OPENAI_GUARDRAIL_MODEL_NAME"
                ),
                "embedding_model_name": os.environ.get(
                    "OPENAI_EMBEDDING_MODEL_NAME", "SAMPLE_OPENAI_EMBEDDING_MODEL_NAME"
                ),
                "context_window": int(os.environ.get("OPENAI_CONTEXT_WINDOW", 100)),
            },
            "azureai_configuration": {
                "api_key": os.environ.get("AZURE_API_KEY", "SAMPLE_AZURE_API_KEY"),
                "type": os.environ.get("AZURE_API_TYPE", "SAMPLE_AZURE_API_TYPE"),
                "base": os.environ.get("AZURE_API_BASE", "SAMPLE_AZURE_API_BASE"),
                "version": os.environ.get("AZURE_API_VERSION", "SAMPLE_AZURE_API_VERSION"),
                "deployment_name": os.environ.get(
                    "AZURE_DEPLOYMENT_NAME", "SAMPLE_AZURE_DEPLOYMENT_NAME"
                ),
                "embedding_deployment_name": os.environ.get(
                    "AZURE_EMBEDDING_DEPLOYMENT_NAME", "SAMPLE_AZURE_EMBEDDING_DEPLOYMENT_NAME"
                ),
                "model_name": os.environ.get("AZURE_MODEL_NAME", "SAMPLE_AZURE_MODEL_NAME"),
            },
            "perplexityai_configuration": {
                "api_key": os.environ.get("PERPLEXITY_API_KEY", "SAMPLE_PERPLEXITY_API_KEY"),
                "model_name": os.environ.get(
                    "PERPLEXITY_MODEL_NAME", "SAMPLE_PERPLEXITY_MODEL_NAME"
                ),
                "api_base": os.environ.get("PERPLEXITY_API_BASE", "SAMPLE_PERPLEXITY_API_BASE"),
            },
            "anthropicai_configuration": {
                "api_key": os.environ.get("ANTHROPIC_API_KEY", "SAMPLE_ANTHROPIC_API_KEY"),
                "model_name": os.environ.get("ANTHROPIC_MODEL_NAME", "SAMPLE_ANTHROPIC_MODEL_NAME"),
            },
            "geminiai_configuration": {
                "api_key": os.environ.get("GEMINI_API_KEY", "SAMPLE_GEMINI_API_KEY"),
                "model_name": os.environ.get("GEMINI_MODEL_NAME", "SAMPLE_GEMINI_MODEL_NAME"),
            },
            "pinecone_configuration": {
                "api_key": os.environ.get("PINECONE_API_KEY", "SAMPLE_PINECONE_API_KEY"),
                "index": os.environ.get("PINECONE_INDEX", "SAMPLE_PINECONE_INDEX"),
                "namespace": os.environ.get("PINECONE_NAMESPACE", "SAMPLE_PINECONE_NAMESPACE"),
                "spec_cloud": os.environ.get("PINECONE_SPEC_CLOUD", "aws"),
                "spec_region": os.environ.get("PINECONE_SPEC_REGION", "us-west-2"),
                "metric": os.environ.get("PINECONE_METRIC", "cosine"),
                "timeout": os.environ.get("PINECONE_TIMEOUT", 10),
            },
            "common_configuration": {
                "max_retries": os.environ.get("MAX_RETRIES", 5),
            },
            "agent_configuration": self._build_agent_configuration(),
            "mongodb_configuration": {
                "host": os.environ.get("MONGODB_HOST", "SAMPLE_MONGODB_HOST"),
                "port": os.environ.get("MONGODB_PORT", 27017),
                "username": os.environ.get("MONGODB_USERNAME", "SAMPLE_MONGODB_USERNAME"),
                "password": os.environ.get("MONGODB_PASSWORD", "SAMPLE_MONGODB_PASSWORD"),
                "db": os.environ.get("MONGODB_DB", "SAMPLE_MONGODB_DB"),
            },
            "postgresql_configuration": {
                "host": os.environ.get("POSTGRES_HOST", "localhost"),
                "port": int(os.environ.get("POSTGRES_PORT", "5432")),
                "username": os.environ.get("POSTGRES_USERNAME", "postgres"),
                "password": os.environ.get("POSTGRES_PASSWORD")
                or os.environ.get("POSTGRES_PASSWRD", "postgres"),
                "db": os.environ.get("POSTGRES_DATABASE", "postgres"),
                "app_schema": os.environ.get("POSTGRES_APP_SCHEMA", "public"),
            },
            "bootstrap_configuration": {
                "app_schema": os.environ.get("POSTGRES_APP_SCHEMA", "public"),
                "alembic_config_path": os.environ.get("ALEMBIC_CONFIG_PATH"),
                "migration_url": os.environ.get("SQLALCHEMY_DATABASE_MIGRATION_URL"),
                "seed_org_id": os.environ.get("BOOTSTRAP_ORG_ID"),
                "seed_org_name": os.environ.get("BOOTSTRAP_ORG_NAME"),
                "seed_org_slug": os.environ.get("BOOTSTRAP_ORG_SLUG"),
            },
            "sqlserver_configuration": {
                "host": os.environ.get("SQLSERVER_HOST", "localhost"),
                "port": int(os.environ.get("SQLSERVER_PORT", 1433)),
                "username": os.environ.get("SQLSERVER_USERNAME", "sa"),
                "password": os.environ.get("SQLSERVER_PASSWRD", "Password123"),
                "db": os.environ.get("SQLSERVER_DB", "master"),
                "app_schema": os.environ.get("SQLSERVER_APP_SCHEMA", "dbo"),
            },
            "sqlite_configuration": {
                "db_path": os.environ.get("SQLITE_DB", "sqlite.db"),
            },
            "opensearch_configuration": {
                "host": os.environ.get("OPENSEARCH_HOST", "localhost"),
                "port": int(os.environ.get("OPENSEARCH_PORT", 9200)),
                "username": os.environ.get("OPENSEARCH_USERNAME", "admin"),
                "password": os.environ.get("OPENSEARCH_PASSWORD", "admin"),
                "use_ssl": os.getenv("OPENSEARCH_USE_SSL", "True").lower() in ("true", "1", "t"),
                "verify_certs": os.getenv("OPENSEARCH_VERIFY_CERTS", "True").lower()
                in ("true", "1", "t"),
                "index_name": os.environ.get("OPENSEARCH_INDEX_NAME", "index"),
            },
            "langfuse_configuration": {
                "env": os.environ.get("LANGFUSE_ENV", "local"),
            },
            "pocketbase_configuration": {
                "url": os.environ.get("POCKETBASE_URL", "http://localhost:8090"),
                "admin_email": os.environ.get("POCKETBASE_ADMIN_USERNAME", "admin@example.com"),
                "admin_password": os.environ.get(
                    "POCKETBASE_ADMIN_PASSWORD", "your_secure_password"
                ),
            },
            # "observability_configuration": {
            #     "enable_otel_collector": os.getenv("ENABLE_OTEL_COLLECTOR", "False").lower() in ("true", "1", "t"),
            #     "otel_agent_hostname": os.environ.get("OTEL_AGENT_HOSTNAME", "http://localhost"),
            #     "otel_http_agent_port": int(os.environ.get("OTEL_HTTP_AGENT_PORT", 4318)),
            #     "otel_grpc_agent_port": int(os.environ.get("OTEL_GRPC_AGENT_PORT", 4317)),
            # },
            "background_jobs_configuration": {
                "redis_queue_name": os.environ.get(
                    "ACTION_RUNS_REDIS_QUEUE_NAME", DEFAULT_ACTION_RUNS_QUEUE
                ),
                "worker_enabled": str(os.environ.get("ACTION_RUNS_WORKER_ENABLED", "false"))
                .strip()
                .lower()
                in {"1", "true", "yes", "on"},
                "worker_backoff_seconds": float(
                    os.environ.get("ACTION_RUNS_WORKER_BACKOFF_SECONDS", "0.1")
                ),
                "redis_blpop_timeout_seconds": int(
                    os.environ.get("ACTION_RUNS_REDIS_BLPOP_TIMEOUT_SECONDS", "1")
                ),
                "retry_sweep_interval_seconds": int(
                    os.environ.get("ACTION_RUNS_RETRY_SWEEP_INTERVAL_SECONDS", "5")
                ),
                "pending_action_run_batch_size": int(
                    os.environ.get("ACTION_RUNS_PENDING_BATCH_SIZE", "25")
                ),
                "worker_shutdown_join_seconds": float(
                    os.environ.get("ACTION_RUNS_WORKER_SHUTDOWN_JOIN_SECONDS", "5.0")
                ),
            },
            "bulk_import_configuration": {
                "worker_enabled": str(os.environ.get("BULK_IMPORT_WORKER_ENABLED", "false"))
                .strip()
                .lower()
                in {"1", "true", "yes", "on"},
                "poll_interval_seconds": float(
                    os.environ.get("BULK_IMPORT_WORKER_POLL_INTERVAL_SECONDS", "2.0")
                ),
                "poll_batch_size": int(
                    os.environ.get("BULK_IMPORT_WORKER_POLL_BATCH_SIZE", "5")
                ),
                "worker_error_backoff_seconds": float(
                    os.environ.get("BULK_IMPORT_WORKER_ERROR_BACKOFF_SECONDS", "5.0")
                ),
                "worker_shutdown_join_seconds": float(
                    os.environ.get("BULK_IMPORT_WORKER_SHUTDOWN_JOIN_SECONDS", "5.0")
                ),
                "sweep_interval_seconds": float(
                    os.environ.get("BULK_IMPORT_SWEEP_INTERVAL_SECONDS", "30.0")
                ),
                "sweep_batch_size": int(
                    os.environ.get("BULK_IMPORT_SWEEP_BATCH_SIZE", "25")
                ),
                "stale_threshold_seconds": int(
                    os.environ.get("BULK_IMPORT_STALE_THRESHOLD_SECONDS", "600")
                ),
                "recent_jobs_limit": int(
                    os.environ.get("BULK_IMPORT_RECENT_JOBS_LIMIT", "50")
                ),
                "commit_batch_size": int(
                    os.environ.get("BULK_IMPORT_COMMIT_BATCH_SIZE", "3")
                ),
            },
            "workflow_configuration": {
                "row_condition_scan_chunk": int(
                    os.environ.get("WORKFLOW_ROW_CONDITION_SCAN_CHUNK", "500")
                ),
                "row_condition_scan_cap": int(
                    os.environ.get("WORKFLOW_ROW_CONDITION_SCAN_CAP", "100000")
                ),
            },
            "remote_files_configuration": {
                "enabled": str(
                    os.environ.get("REMOTE_FILES_ENABLED", "true")
                ).strip().lower() in {"1", "true", "yes", "on"},
                "fetch_concurrency": int(
                    os.environ.get("REMOTE_FILES_FETCH_CONCURRENCY", "8")
                ),
                "timeout_seconds": float(
                    os.environ.get("REMOTE_FILES_TIMEOUT_SECONDS", "15.0")
                ),
                "max_size_bytes": int(
                    os.environ.get("REMOTE_FILES_MAX_SIZE_BYTES", str(20 * 1024 * 1024))
                ),
                "max_redirects": int(
                    os.environ.get("REMOTE_FILES_MAX_REDIRECTS", "3")
                ),
            },
            "filehandler_configuration": {
                "entity_type_slug_max_length": int(
                    os.environ.get("FILEHANDLER_ENTITY_TYPE_SLUG_MAX_LENGTH", "64")
                ),
            },
            "entity_relations_configuration": {
                # Allowed values must match entities.models.interface.RelationType.
                # Kept as a literal set here (not imported) — common/configuration.py
                # must not depend on a domain module.
                "default_relation_type": self._validate_choice_env(
                    "ENTITY_RELATIONS_DEFAULT_RELATION_TYPE",
                    "SNAPSHOT",
                    frozenset({"REFERENCE", "SNAPSHOT"}),
                ),
            },
            "redis_configuration": {
                "host": os.environ.get("REDIS_HOST", "localhost"),
                "port": int(os.environ.get("REDIS_PORT", "6379")),
                "db": int(os.environ.get("REDIS_DB", "0")),
                "password": os.environ.get("REDIS_PASSWORD", None),
                "queue_name": os.environ.get("REDIS_QUEUE_NAME", "transcription_jobs"),
                # 30 minutes
                "cache_ttl_seconds": int(os.environ.get("REDIS_CACHE_TTL_SECONDS", "5")),
                "cache_pool_max_size": int(os.environ.get("REDIS_CACHE_POOL_MAX_SIZE", "20")),
                "cache_namespace": os.environ.get("REDIS_CACHE_NAMESPACE", "main"),
            },
            "google_oauth_configuration": {
                "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
                "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
                "redirect_uri": os.environ.get("GOOGLE_REDIRECT_URI", ""),
                "allowed_domain": os.environ.get("GOOGLE_ALLOWED_DOMAIN", ""),
            },
            "app_settings": {
                "environment": os.environ.get("ENV", "development"),
                "allow_registration": os.environ.get("ALLOW_REGISTRATION", "true").lower()
                == "true",
                "frontend_url": os.environ.get("FRONTEND_URL", ""),
                "refresh_token_expire_days": int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7")),
            },
            "llm_validation_configuration": {
                "openai_model": os.environ.get("LLM_VALIDATION_MODEL_OPENAI", "gpt-4o-mini"),
                "anthropic_model": os.environ.get(
                    "LLM_VALIDATION_MODEL_ANTHROPIC", "claude-haiku-3-5-20241022"
                ),
                "google_gemini_model": os.environ.get(
                    "LLM_VALIDATION_MODEL_GOOGLE_GEMINI", "gemini/gemini-1.5-flash"
                ),
            },
            "default_roles_configuration": {
                "superadmin_display_name": os.environ.get("ROLE_SUPERADMIN_DISPLAY_NAME", "Super Administrator"),
                "superadmin_priority": int(os.environ.get("ROLE_SUPERADMIN_PRIORITY", "1000")),
                "superadmin_color": os.environ.get("ROLE_SUPERADMIN_COLOR", "#7C3AED"),
                "admin_display_name": os.environ.get("ROLE_ADMIN_DISPLAY_NAME", "Admin"),
                "admin_priority": int(os.environ.get("ROLE_ADMIN_PRIORITY", "100")),
                "admin_color": os.environ.get("ROLE_ADMIN_COLOR", "#DC2626"),
                "viewer_display_name": os.environ.get("ROLE_VIEWER_DISPLAY_NAME", "Viewer"),
                "viewer_priority": int(os.environ.get("ROLE_VIEWER_PRIORITY", "10")),
                "viewer_color": os.environ.get("ROLE_VIEWER_COLOR", "#6B7280"),
            },
            "sla_configuration": {
                "warning_hours": float(os.environ.get("SLA_WARNING_HOURS", "8")),
                "critical_hours": float(os.environ.get("SLA_CRITICAL_HOURS", "2")),
            },
            "auth_configuration": {
                "bypass_auth": os.environ.get("BYPASS_AUTH", "False").lower() in ("true", "1", "t"),
                "public_email_domains": [
                    d.strip().lower()
                    for d in os.environ.get(
                        "PUBLIC_EMAIL_DOMAINS",
                        self._config.get("AUTH_CONFIG", "public_email_domains", fallback=""),
                    )
                    .replace(";", ",")
                    .split(",")
                    if d.strip()
                ],
                "default_org_id": os.environ.get(
                    "DEFAULT_ORG_ID", "00000000-0000-0000-0000-000000000001"
                ).strip(),
                "platform_org_id": os.environ.get(
                    "PLATFORM_ORG_ID", "00000000-0000-0000-0000-000000000000"
                ).strip(),
            },
            "custom_oauth_configuration": {
                "secret_key": os.environ.get(
                    "CUSTOM_OAUTH_SECRET_KEY", "ADD_CUSTOM_OAUTH_SECRET_KEY"
                ),
                "algorithm": os.environ.get("CUSTOM_OAUTH_ALGORITHM", "HS256"),
                "access_token_expire_seconds": int(
                    os.environ.get("CUSTOM_OAUTH_ACCESS_TOKEN_EXPIRE_SECONDS", 3600)
                ),
                "refresh_token_expire_seconds": int(
                    os.environ.get("CUSTOM_OAUTH_REFRESH_TOKEN_EXPIRE_SECONDS", 86400)
                ),
                "bootstrap_admin_email": self._env_required_str("BOOTSTRAP_ADMIN_EMAIL"),
                "bootstrap_admin_password": self._env_required_str("BOOTSTRAP_ADMIN_PASSWORD"),
                "bootstrap_super_admin_email": self._env_required_str(
                    "BOOTSTRAP_SUPER_ADMIN_EMAIL"
                ),
                "bootstrap_super_admin_password": self._env_required_str(
                    "BOOTSTRAP_SUPER_ADMIN_PASSWORD"
                ),
            },
            "audit_log_configuration": {
                "group": os.environ.get("AUDIT_LOG_GROUP", "audit_g"),
                "consumer": os.environ.get(
                    "AUDIT_LOG_CONSUMER", f"{socket.gethostname()}:{os.getpid()}"
                ),
                "stream": os.environ.get("AUDIT_LOG_STREAM", "audit:events"),
                # Maximum batch size for bulk processing
                "batch_size": int(os.environ.get("AUDIT_LOG_BATCH_SIZE", 100)),
                # wait up to AUDIT_LOG_BLOCK_MS seconds for new messages
                "block_ms": int(os.environ.get("AUDIT_LOG_BLOCK_MS", 2000)),
                # Minimum batch size before processing (unless timeout)
                "min_batch_size": int(os.environ.get("AUDIT_LOG_MIN_BATCH_SIZE", 5)),
                # Max time to wait before processing any accumulated messages
                "batch_timeout": float(os.environ.get("AUDIT_LOG_BATCH_TIMEOUT", 5.0)),
            },
            "smtp_configuration": {
                "host": os.environ.get("SMTP_HOST", "YOUR_SMTP_HOST"),
                "port": int(os.environ.get("SMTP_PORT", "465")),
                "username": os.environ.get("SMTP_USERNAME", "YOUR_SMTP_USERNAME"),
                "password": os.environ.get("SMTP_PASSWORD", "YOUR_SMTP_PASSWORD"),
                "use_tls": os.environ.get("SMTP_USE_TLS", "True").lower() in ("true", "1", "t"),
                "from_email": os.environ.get("SMTP_FROM_EMAIL", "YOUR_SMTP_FROM_EMAIL"),
                "from_name": os.environ.get("SMTP_FROM_NAME", "YOUR_SMTP_FROM_NAME"),
                "reply_to_email": os.environ.get("SMTP_REPLY_TO_EMAIL", "YOUR_SMTP_REPLY_TO_EMAIL"),
                "mail_to": os.environ.get("SMTP_MAIL_TO", "YOUR_SMTP_MAIL_TO"),
                "run_real_email_delivery_test": os.environ.get(
                    "RUN_REAL_EMAIL_DELIVERY_TEST", "False"
                ).lower()
                in ("true", "1", "t"),
            },
            "microsoft_oauth_configuration": {
                "enabled": self._read_strict_bool_env("ENABLE_MICROSOFT_SSO", True),
                "client_id": os.environ.get(
                    "MICROSOFT_OAUTH_CLIENT_ID", "ADD_MICROSOFT_OAUTH_CLIENT_ID"
                ),
                "tenant_id": os.environ.get(
                    "MICROSOFT_OAUTH_TENANT_ID", "ADD_MICROSOFT_OAUTH_TENANT_ID"
                ),
                # Optional: when unset the app uses the public-client (PKCE) flow.
                "client_secret": os.environ.get("MICROSOFT_OAUTH_CLIENT_SECRET", ""),
                "redirect_uri": os.environ.get(
                    "MICROSOFT_OAUTH_REDIRECT_URI", "http://localhost:5173/auth/microsoft/callback"
                ),
                "state_secret": os.environ.get(
                    "MICROSOFT_OAUTH_STATE_SECRET",
                    os.environ.get("JWT_SECRET_KEY", "microsoft-state-secret"),
                ),
                "state_ttl_seconds": int(
                    os.environ.get("MICROSOFT_OAUTH_STATE_TTL_SECONDS", "600")
                ),
            },
            "cognito_configuration": {
                "domain": os.environ.get("COGNITO_DOMAIN", "ADD_COGNITO_DOMAIN"),
                "region": os.environ.get("COGNITO_REGION", "us-east-1"),
                "user_pool_id": os.environ.get("COGNITO_USER_POOL_ID", "ADD_COGNITO_USER_POOL_ID"),
                "client_id": os.environ.get("COGNITO_CLIENT_ID", "ADD_COGNITO_CLIENT_ID"),
                "client_secret": os.environ.get("COGNITO_CLIENT_SECRET", None),
                "redirect_uri": os.environ.get(
                    "COGNITO_REDIRECT_URI", "http://localhost:3000/auth/cognito/callback"
                ),
                "scopes": os.environ.get("COGNITO_SCOPES", "openid profile email").split(),
                "auth_path": os.environ.get("COGNITO_AUTH_PATH", "/oauth2/authorize"),
                "token_path": os.environ.get("COGNITO_TOKEN_PATH", "/oauth2/token"),
                "allowed_email_domains": os.environ.get("COGNITO_ALLOWED_EMAIL_DOMAINS", "").split(
                    ","
                )
                if os.environ.get("COGNITO_ALLOWED_EMAIL_DOMAINS")
                else [],
                "secret_key": os.environ.get("COGNITO_SECRET_KEY")
                or os.environ.get("CUSTOM_OAUTH_SECRET_KEY", "ADD_COGNITO_SECRET_KEY"),
                "algorithm": os.environ.get(
                    "COGNITO_ALGORITHM", os.environ.get("CUSTOM_OAUTH_ALGORITHM", "HS256")
                ),
                "access_token_expire_seconds": int(
                    os.environ.get("COGNITO_ACCESS_TOKEN_EXPIRE_SECONDS")
                    or os.environ.get("CUSTOM_OAUTH_ACCESS_TOKEN_EXPIRE_SECONDS", 3600)
                ),
                "refresh_token_expire_seconds": int(
                    os.environ.get("COGNITO_REFRESH_TOKEN_EXPIRE_SECONDS")
                    or os.environ.get("CUSTOM_OAUTH_REFRESH_TOKEN_EXPIRE_SECONDS", 86400)
                ),
            },
            "aws_configuration": {
                "aws_access_key_id": os.environ.get("AWS_ACCESS_KEY_ID", None),
                "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY", None),
            },
            "s3_configuration": {
                "bucket_name": os.environ.get("S3_BUCKET_NAME", ""),
                "region": os.environ.get("S3_REGION", "us-east-1"),
                "validated_datasets_prefix": os.environ.get(
                    "S3_VALIDATED_DATASETS_PREFIX", "validated_datasets"
                ),
                "invalidated_datasets_prefix": os.environ.get(
                    "S3_INVALIDATED_DATASETS_PREFIX", "invalidated_datasets"
                ),
                "industry_validated_datasets_prefix": os.environ.get(
                    "S3_INDUSTRY_VALIDATED_DATASETS_PREFIX", "industry_validated_datasets"
                ),
                "industry_invalidated_datasets_prefix": os.environ.get(
                    "S3_INDUSTRY_INVALIDATED_DATASETS_PREFIX", "industry_invalidated_datasets"
                ),
                "enabled": os.environ.get("S3_ENABLED", "true").lower() == "true",
                "multipart_enabled": os.environ.get("S3_MULTIPART_ENABLED", "true").lower()
                == "true",
                "multipart_threshold": int(os.environ.get("S3_MULTIPART_THRESHOLD", "26214400")),
                "multipart_chunksize": int(os.environ.get("S3_MULTIPART_CHUNKSIZE", "26214400")),
                "max_concurrency": int(os.environ.get("S3_MAX_CONCURRENCY", "10")),
                "use_threads": os.environ.get("S3_USE_THREADS", "true").lower() == "true",
                "presigned_url_expiration": int(
                    os.environ.get("S3_PRESIGNED_URL_EXPIRATION", "3600")
                ),
                "artifacts_bucket": os.environ.get("S3_ARTIFACTS_BUCKET", ""),
                "artifacts_prefix": os.environ.get("S3_ARTIFACTS_PREFIX", "mmm_models"),
                "training_response_filename": os.environ.get(
                    "S3_TRAINING_RESPONSE_FILENAME", "training_response.json"
                ),
                "plots_filename": os.environ.get("S3_PLOTS_FILENAME", "plots.json"),
                "model_filename": os.environ.get("S3_MODEL_FILENAME", "model.json"),
                "facts_directory": os.environ.get("S3_FACTS_DIRECTORY", "facts"),
                "manifest_filename": os.environ.get("S3_MANIFEST_FILENAME", "manifest.json"),
                "summary_filename": os.environ.get("S3_SUMMARY_FILENAME", "summary.json"),
            },
            "dataset_configuration": {
                "chunk_size_rows": int(os.environ.get("CSV_CHUNK_SIZE", "100000")),
                "chunk_threshold_bytes": int(os.environ.get("CSV_CHUNK_THRESHOLD", "104857600")),
                "allowed_extensions": [
                    ext.strip()
                    for ext in os.environ.get("DATASET_ALLOWED_EXTENSIONS", ".csv").split(",")
                    if ext.strip()
                ],
                "date_format": os.environ.get("DATASET_DATE_FORMAT", "%Y-%m-%d"),
                "min_years_history": int(os.environ.get("DATASET_MIN_YEARS_HISTORY", "2")),
                "prefix_kpi": os.environ.get("DATASET_PREFIX_KPI", "kpi_"),
                "prefix_media": os.environ.get("DATASET_PREFIX_MEDIA", "m_"),
                "prefix_competitor": os.environ.get("DATASET_PREFIX_COMPETITOR", "c_"),
                "prefix_base": os.environ.get("DATASET_PREFIX_BASE", "base_"),
                "min_rows_daily": int(os.environ.get("DATASET_MIN_ROWS_DAILY", "60")),
                "min_rows_weekly": int(os.environ.get("DATASET_MIN_ROWS_WEEKLY", "16")),
                "min_rows_monthly": int(os.environ.get("DATASET_MIN_ROWS_MONTHLY", "24")),
            },
            "mmm_service_configuration": {
                "service_url": os.environ.get("MMM_SERVICE_URL", "http://localhost:8000"),
                "timeout_seconds": int(os.environ.get("MMM_SERVICE_TIMEOUT", 600)),
                "train_endpoint": os.environ.get("MMM_SERVICE_TRAIN_ENDPOINT", "/unified/train"),
                "retrain_endpoint": os.environ.get(
                    "MMM_SERVICE_RETRAIN_ENDPOINT", "/unified/retrain"
                ),
                "budget_optimisation_endpoint": os.environ.get(
                    "MMM_SERVICE_BUDGET_OPTIMISATION_ENDPOINT", "/budget_optimisation"
                ),
                "forecasting_endpoint": os.environ.get(
                    "MMM_SERVICE_FORECASTING_ENDPOINT", "/forecasting"
                ),
                "quick_start_budget_optimisation_endpoint": os.environ.get(
                    "MMM_SERVICE_QUICK_START_BUDGET_OPTIMISATION_ENDPOINT",
                    "/inference/quick-start/budget-optimization",
                ),
            },
            "mmm_version_comparison_configuration": {
                "model_name": os.environ.get(
                    "MMM_VERSION_COMPARISON_MODEL_NAME",
                    os.environ.get("OPENAI_MODEL_NAME", "SAMPLE_OPENAI_MODEL_NAME"),
                ),
                "temperature": float(os.environ.get("MMM_VERSION_COMPARISON_TEMPERATURE", 0.7)),
                "max_completion_tokens": int(
                    os.environ.get("MMM_VERSION_COMPARISON_MAX_COMPLETION_TOKENS", 2000)
                ),
            },
            "explainability_configuration": {
                "chart_facts_model_name": os.environ.get(
                    "EXPLAINABILITY_CHART_FACTS_MODEL_NAME",
                    os.environ.get("OPENAI_MODEL_NAME", "SAMPLE_OPENAI_MODEL_NAME"),
                ),
                "chart_facts_temperature": float(
                    os.environ.get("EXPLAINABILITY_CHART_FACTS_TEMPERATURE", 0.5)
                ),
                "chart_facts_max_completion_tokens": int(
                    os.environ.get("EXPLAINABILITY_CHART_FACTS_MAX_COMPLETION_TOKENS", 10000)
                ),
                "summary_facts_model_name": os.environ.get(
                    "EXPLAINABILITY_SUMMARY_FACTS_MODEL_NAME",
                    os.environ.get("OPENAI_MODEL_NAME", "SAMPLE_OPENAI_MODEL_NAME"),
                ),
                "summary_facts_temperature": float(
                    os.environ.get("EXPLAINABILITY_SUMMARY_FACTS_TEMPERATURE", 0.3)
                ),
                "summary_facts_max_completion_tokens": int(
                    os.environ.get("EXPLAINABILITY_SUMMARY_FACTS_MAX_COMPLETION_TOKENS", 10000)
                ),
            },
            "security_configuration": {
                "jwt_secret_key": self._env_required_str(
                    "JWT_SECRET_KEY",
                    min_length=JWT_MIN_SECRET_LENGTH,
                    forbidden_values=JWT_FORBIDDEN_SECRET_VALUES,
                ),
                "jwt_algorithm": os.environ.get("JWT_ALGORITHM", "HS256"),
                "access_token_expire_minutes": int(
                    os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
                ),
                "refresh_token_expire_days": int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7")),
            },
        }
        self._configuration = ConfigurationModel(**config_obj)

    @staticmethod
    def _env_required_str(
        name: str,
        min_length: int = 0,
        forbidden_values: frozenset[str] = frozenset(),
    ) -> str:
        """Resolve a required string env var.

        Raises ValueError if missing, blank, too short, or a known placeholder
        value (e.g. one shipped in an env.example template).
        """
        raw = os.environ.get(name, "")
        normalized = str(raw).strip()
        if not normalized or normalized.lower() in {"none", "null"}:
            raise ValueError(
                f"Required environment variable '{name}' is not set. App cannot start."
            )
        if len(normalized) < min_length:
            raise ValueError(
                f"Environment variable '{name}' must be at least {min_length} characters."
            )
        if normalized.lower() in forbidden_values:
            raise ValueError(
                f"Environment variable '{name}' is still set to a known placeholder "
                "value from a template file. Set a real, unique value before starting the app."
            )
        return normalized

    @staticmethod
    def _read_strict_bool_env(name: str, default: bool) -> bool:
        """Read boolean env vars using strict true/false parsing only."""
        raw = os.environ.get(name, str(default)).strip().lower()
        if raw == "true":
            return True
        if raw == "false":
            return False
        raise ValueError(f"Invalid boolean value for {name}: '{raw}'. Use 'true' or 'false'.")

    @staticmethod
    def _validate_choice_env(name: str, default: str, allowed: frozenset[str]) -> str:
        """Read an env var and validate it against a fixed set of allowed values.

        Fails at startup instead of deferring to whatever code first tries to
        interpret the value (e.g. materializing it into a domain enum)."""
        raw = os.environ.get(name, default).strip()
        if raw not in allowed:
            raise ValueError(
                f"Invalid value for {name}: '{raw}'. Must be one of: {', '.join(sorted(allowed))}."
            )
        return raw

    def _build_agent_configuration(self) -> dict[str, object]:
        """Build the startup configuration payload for the agent module.

        Returns:
            The resolved agent configuration payload.
        """
        system_agents_file = os.environ.get(
            "AGENT_SYSTEM_AGENTS_FILE",
            str(Path(__file__).resolve().with_name("system_agents.json")),
        )
        with Path(system_agents_file).open("r", encoding="utf-8") as handle:
            system_agent_templates = json.load(handle)
        return {
            "system_agents_file": system_agents_file,
            "system_agent_templates": system_agent_templates,
        }


_configuration_instance = Configuration()


def get_configuration():
    """Return the shared configuration payload."""
    return _configuration_instance._configuration


def get_config_ini():
    """Return the shared parsed config.ini object."""
    return _configuration_instance._config


def get_database_url() -> str:
    """Return the required database URL from environment."""
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise ValueError("DATABASE_URL must be set")
    return database_url
