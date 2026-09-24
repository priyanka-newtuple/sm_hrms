from enum import Enum, StrEnum
from typing import Any

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict, Field

# Default Redis queue names — single source of truth shared by the configuration
# layer, the Pydantic config defaults, and the worker managers' fallbacks.
DEFAULT_ACTION_RUNS_QUEUE = "action_runs_jobs"
# Dedicated queue for standalone async agent runs (POST /agent/async_runs). Kept
# separate from the entity/workflow action-runs queue so the two never contend.
DEFAULT_AGENT_ASYNC_QUEUE = "agent_async_runs"


class ExtendedEnum(Enum):
    """Extended Enum class with a method to list all values."""

    @classmethod
    def list(cls):
        return [c.value for c in cls]


class ExtendedStrEnum(StrEnum):
    """Extended StrEnum class with a method to list all values."""

    @classmethod
    def list(cls):
        """Lists all values of the enum."""
        return [c.value for c in cls]


class BaseModel(PydanticBaseModel):
    """Base model for all data models"""

    model_config = ConfigDict(
        populate_by_name=True,
        # validate_assignment=True,
        from_attributes=True,
        arbitrary_types_allowed=True,
        protected_namespaces=(),
    )


class LoggerConfiguration(BaseModel):
    """Represents the logger configuration"""

    log_level: str
    enable_rich_logger: int
    enable_json_filelogger: int
    log_dir: str


class ServerConfiguration(BaseModel):
    """Represents the server configuration"""

    host: str
    port: str
    proxy_url: str
    request_timeout_seconds: int


class RuntimeConfiguration(BaseModel):
    """Runtime configuration shared across modules."""

    sql_echo: bool
    encryption_key: str
    frontend_url: str
    litellm_model: str = ""
    litellm_api_base: str = ""
    inbound_email_domain: str
    inbound_email_webhook_secret: str
    inbound_email_allowed_bucket: str
    inbound_email_s3_region: str
    inbound_email_s3_access_key_id: str
    inbound_email_s3_secret_access_key: str


class OpenAIConfiguration(BaseModel):
    """Represents the OpenAI configuration"""

    api_key: str
    model_name: str
    guardrail_model_name: str
    embedding_model_name: str
    context_window: int


class AzureAIConfiguration(BaseModel):
    """Represents the AzureAI configuration"""

    api_key: str
    type: str
    base: str
    version: str
    deployment_name: str
    embedding_deployment_name: str
    model_name: str


class PerplexityAIConfiguration(BaseModel):
    """Represents the Perplexity configuration"""

    api_key: str
    model_name: str
    api_base: str


class AnthropicAIConfiguration(BaseModel):
    """Represents the Anthropic configuration"""

    api_key: str
    model_name: str


class GeminiAIConfiguration(BaseModel):
    """Represents the Anthropic configuration"""

    api_key: str
    model_name: str


class MongoDBConfiguration(BaseModel):
    """Represents the MongoDB configuration"""

    host: str
    port: int
    username: str
    password: str
    db: str


class PostgreSQLConfiguration(BaseModel):
    """Represents the PostgreSQL configuration"""

    host: str
    port: int
    username: str
    password: str
    db: str
    app_schema: str


class BootstrapConfiguration(BaseModel):
    """Represents modular backend bootstrap configuration."""

    app_schema: str
    alembic_config_path: str | None = None
    migration_url: str | None = None
    seed_org_id: str | None = None
    seed_org_name: str | None = None
    seed_org_slug: str | None = None


class SQLServerConfiguration(BaseModel):
    """Represents the SQLServer configuration"""

    host: str
    port: int
    username: str
    password: str
    db: str
    app_schema: str


class SQLiteConfiguration(BaseModel):
    """Represents the SQLite configuration"""

    db_path: str


class OpenSearchConfiguration(BaseModel):
    """Represents the OpenSearch configuration"""

    host: str
    username: str
    password: str
    use_ssl: bool
    verify_certs: bool
    index_name: str


class LangfuseConfiguration(BaseModel):
    """Represents the Langfuse configuration"""

    env: str


class CommonConfiguration(BaseModel):
    """Represents the common configuration"""

    max_retries: int


class BackgroundJobsConfiguration(BaseModel):
    """Represents configuration for the background jobs module."""

    redis_queue_name: str = DEFAULT_ACTION_RUNS_QUEUE
    # When True, this process runs the action-runs worker + retry-sweep threads.
    # Enabled only on the dedicated modular-worker container.
    worker_enabled: bool = False
    # Worker loop tuning (seconds, except batch size).
    worker_backoff_seconds: float = 0.1  # idle/error backoff between worker iterations
    redis_blpop_timeout_seconds: int = 1  # blocking pop wait before local fallback
    retry_sweep_interval_seconds: int = 5  # retry + timeout sweep cadence
    pending_action_run_batch_size: int = 25  # max pending action runs fetched per sweep
    worker_shutdown_join_seconds: float = 5.0  # max wait to join worker/sweep threads on stop()


class BulkImportConfiguration(BaseModel):
    """Represents configuration for the bulk_import module."""

    # When True, this process runs the bulk-import worker + stale-job-sweep
    # threads. Enabled only on the dedicated modular-worker container, same
    # pattern as background_jobs_configuration.worker_enabled.
    worker_enabled: bool = False
    # Worker poll loop tuning (seconds, except batch size).
    poll_interval_seconds: float = 2.0  # idle wait between polls when no job was found
    poll_batch_size: int = 5  # max QUEUED jobs fetched per poll
    worker_error_backoff_seconds: float = 5.0  # backoff after an unexpected loop error
    worker_shutdown_join_seconds: float = 5.0  # max wait to join worker/sweep threads on stop()
    # Stale-job sweep tuning.
    sweep_interval_seconds: float = 30.0  # sweep cadence
    sweep_batch_size: int = 25  # max stale jobs force-resolved per sweep
    stale_threshold_seconds: int = 600  # how long a job may sit PROCESSING/COMMITTING
    # Cap on the recent-imports list — a resume/status view, not a full
    # paginated job history browser.
    recent_jobs_limit: int = 50
    # Final commit works in small record batches so remote attachments can be
    # fetched concurrently without delaying every entity behind the full file set.
    commit_batch_size: int = 3


class WorkflowConfiguration(BaseModel):
    """Represents configuration for the workflow module."""

    # Raw rows read per round, and in total, when an actor's read policy carries
    # row-level conditions that can only be evaluated on a loaded row, so
    # enrollment pages and aggregates must be sliced after filtering.
    row_condition_scan_chunk: int = 500
    row_condition_scan_cap: int = 100_000


class RemoteFilesConfiguration(BaseModel):
    """Configuration for securely retrieving externally hosted files."""

    enabled: bool = True
    fetch_concurrency: int = 8
    timeout_seconds: float = 15.0
    max_size_bytes: int = 20 * 1024 * 1024
    max_redirects: int = 3


class FilehandlerConfiguration(BaseModel):
    """Represents configuration for the filehandler module."""

    entity_type_slug_max_length: int


class EntityRelationsConfiguration(BaseModel):
    """Represents configuration for the entities module's field-inheritance relations."""

    default_relation_type: str


class AgentConfiguration(BaseModel):
    """Represents startup configuration for the agent module."""

    system_agents_file: str
    system_agent_templates: list[dict[str, Any]] = Field(default_factory=list)


class PocketBaseConfiguration(BaseModel):
    """Represents the PocketBase configuration"""

    url: str
    admin_email: str
    admin_password: str


class AWSConfiguration(BaseModel):
    """Represents the AWS configuration for Cognito admin operations"""

    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None


class S3Configuration(BaseModel):
    """S3 storage configuration"""

    bucket_name: str
    region: str
    validated_datasets_prefix: str
    invalidated_datasets_prefix: str
    industry_validated_datasets_prefix: str
    industry_invalidated_datasets_prefix: str
    enabled: bool
    multipart_enabled: bool
    multipart_threshold: int
    multipart_chunksize: int
    max_concurrency: int
    use_threads: bool
    presigned_url_expiration: int
    artifacts_bucket: str
    artifacts_prefix: str
    training_response_filename: str
    plots_filename: str
    model_filename: str
    facts_directory: str
    manifest_filename: str
    summary_filename: str


class PineconeConfiguation(BaseModel):
    """Represents the Pinecone configuration"""

    api_key: str
    index: str
    namespace: str
    spec_cloud: str
    spec_region: str
    metric: str
    timeout: int


class AzureAISearchConfiguration(BaseModel):
    """Represents the AzureAISearch configuration"""

    endpoint: str
    key: str
    index_name: str
    semantic_configuration_name: str


# class ObservabilityConfiguration(BaseModel):
#     """Represents the Observability configuration"""
#     enable_otel_collector: bool
#     otel_agent_hostname: str
#     otel_http_agent_port: int
#     otel_grpc_agent_port: int


class CustomOAuthConfiguration(BaseModel):
    """Represents the Custom OAuth configuration"""

    secret_key: str
    algorithm: str
    access_token_expire_seconds: int
    refresh_token_expire_seconds: int
    bootstrap_admin_email: str
    bootstrap_admin_password: str
    bootstrap_super_admin_email: str
    bootstrap_super_admin_password: str


class GoogleOAuthConfiguration(BaseModel):
    """Google OAuth2 configuration."""

    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = ""
    allowed_domain: str = ""


class AppSettings(BaseModel):
    """General application runtime settings."""

    environment: str = "development"
    allow_registration: bool = True
    frontend_url: str = ""
    refresh_token_expire_days: int = 7


class LLMValidationConfiguration(BaseModel):
    """Models used for cheaply validating LLM provider API keys."""

    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-haiku-3-5-20241022"
    google_gemini_model: str = "gemini/gemini-1.5-flash"


class SLAConfiguration(BaseModel):
    """Default SLA risk thresholds used when a view definition has no sla_config."""

    warning_hours: float = 8.0
    critical_hours: float = 2.0


class AuthConfiguration(BaseModel):
    """Auth-related configuration."""

    bypass_auth: bool
    public_email_domains: list[str]
    default_org_id: str
    platform_org_id: str


class DefaultRolesConfiguration(BaseModel):
    """Display configuration for default system roles seeded per organization."""

    superadmin_display_name: str = "Super Administrator"
    superadmin_priority: int = 1000
    superadmin_color: str = "#7C3AED"
    admin_display_name: str = "Admin"
    admin_priority: int = 100
    admin_color: str = "#DC2626"
    viewer_display_name: str = "Viewer"
    viewer_priority: int = 10
    viewer_color: str = "#6B7280"


class RedisConfiguration(BaseModel):
    """Represents the Redis configuration"""

    host: str
    port: int
    db: int
    password: str | None = None
    queue_name: str = "transcription_jobs"
    cache_ttl_seconds: int
    cache_pool_max_size: int
    cache_namespace: str


class AuditLogConfiguration(BaseModel):
    """Represents the Audit Log configuration"""

    group: str
    consumer: str
    stream: str
    batch_size: int
    block_ms: int
    min_batch_size: int
    batch_timeout: int


class SMTPConfiguration(BaseModel):
    """Represents the SMTP configuration for email sending"""

    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    from_email: str
    from_name: str
    reply_to_email: str
    mail_to: str
    run_real_email_delivery_test: bool


class MicrosoftOAuthConfiguration(BaseModel):
    """Represents the Microsoft OAuth configuration"""

    enabled: bool = True
    client_id: str
    tenant_id: str
    client_secret: str
    redirect_uri: str
    state_secret: str
    state_ttl_seconds: int = 600


class CognitoOAuthConfiguration(BaseModel):
    """Represents the AWS Cognito OAuth configuration"""

    domain: str
    region: str
    user_pool_id: str
    client_id: str
    client_secret: str | None = None
    redirect_uri: str
    scopes: list[str]
    auth_path: str
    token_path: str
    allowed_email_domains: list[str] = []
    # Token creation settings for application tokens (after Cognito authentication)
    secret_key: str
    algorithm: str
    access_token_expire_seconds: int
    refresh_token_expire_seconds: int


class MMMServiceConfiguration(BaseModel):
    """Represents the MMM service configuration"""

    service_url: str
    timeout_seconds: int
    train_endpoint: str
    retrain_endpoint: str
    budget_optimisation_endpoint: str
    forecasting_endpoint: str
    quick_start_budget_optimisation_endpoint: str


class MMMVersionComparisonConfiguration(BaseModel):
    """Represents the MMM version comparison LLM configuration"""

    model_name: str
    temperature: float
    max_completion_tokens: int


class DatasetConfiguration(BaseModel):
    """Dataset processing configuration"""

    chunk_size_rows: int
    chunk_threshold_bytes: int
    allowed_extensions: list[str]
    date_format: str
    min_years_history: int
    prefix_kpi: str
    prefix_media: str
    prefix_competitor: str
    prefix_base: str
    min_rows_daily: int
    min_rows_weekly: int
    min_rows_monthly: int


class ExplainabilityConfiguration(BaseModel):
    """Explainability facts generation configuration"""

    chart_facts_model_name: str
    chart_facts_temperature: float
    chart_facts_max_completion_tokens: int
    summary_facts_model_name: str
    summary_facts_temperature: float
    summary_facts_max_completion_tokens: int


class SecurityConfiguration(BaseModel):
    """Represents the security configuration"""

    jwt_secret_key: str
    jwt_algorithm: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int


class Configuration(BaseModel):
    """Represents the configuration"""

    application_name: str
    environment: str
    logger_configuration: LoggerConfiguration
    openai_configuration: OpenAIConfiguration
    server_configuration: ServerConfiguration
    runtime_configuration: RuntimeConfiguration

    azureai_configuration: AzureAIConfiguration
    perplexityai_configuration: PerplexityAIConfiguration
    anthropicai_configuration: AnthropicAIConfiguration
    geminiai_configuration: GeminiAIConfiguration
    common_configuration: CommonConfiguration
    agent_configuration: AgentConfiguration
    mongodb_configuration: MongoDBConfiguration
    postgresql_configuration: PostgreSQLConfiguration
    bootstrap_configuration: BootstrapConfiguration
    sqlserver_configuration: SQLServerConfiguration
    sqlite_configuration: SQLiteConfiguration
    opensearch_configuration: OpenSearchConfiguration

    pinecone_configuration: PineconeConfiguation

    langfuse_configuration: LangfuseConfiguration
    pocketbase_configuration: PocketBaseConfiguration
    custom_oauth_configuration: CustomOAuthConfiguration
    google_oauth_configuration: GoogleOAuthConfiguration
    app_settings: AppSettings
    microsoft_oauth_configuration: MicrosoftOAuthConfiguration
    cognito_configuration: CognitoOAuthConfiguration
    aws_configuration: AWSConfiguration
    s3_configuration: S3Configuration
    dataset_configuration: DatasetConfiguration
    mmm_service_configuration: MMMServiceConfiguration | None
    mmm_version_comparison_configuration: MMMVersionComparisonConfiguration

    background_jobs_configuration: BackgroundJobsConfiguration
    bulk_import_configuration: BulkImportConfiguration
    workflow_configuration: WorkflowConfiguration
    remote_files_configuration: RemoteFilesConfiguration
    filehandler_configuration: FilehandlerConfiguration
    entity_relations_configuration: EntityRelationsConfiguration
    redis_configuration: RedisConfiguration
    audit_log_configuration: AuditLogConfiguration
    smtp_configuration: SMTPConfiguration
    explainability_configuration: ExplainabilityConfiguration
    llm_validation_configuration: LLMValidationConfiguration
    default_roles_configuration: DefaultRolesConfiguration
    sla_configuration: SLAConfiguration
    auth_configuration: AuthConfiguration
    security_configuration: SecurityConfiguration


class LangfuseMetaData(BaseModel):
    """Represents the metadata for Langfuse generations"""

    generation_name: str | None = None
    generation_id: str | None = None
    parent_observation_id: str | None = None
    version: str | None = None
    trace_user_id: str | None = None
    session_id: str | None = None
    tags: list[str] | None = None
    trace_name: str | None = None
    trace_id: str | None = None
    trace_metadata: dict[str, Any] | None = None
    trace_version: str | None = None
    trace_release: str | None = None
    existing_trace_id: str | None = None
    update_trace_keys: list[str] | None = None
    debug_langfuse: bool | None = None
    mask_input: bool | None = None


class QueryContext(BaseModel):
    """Represents the query context"""

    query: str
    role: str
    stream_response: Any


# region Constants


class Roles(ExtendedStrEnum):
    "Represents roles"

    admin = "Admin"
    basic = "Basic"
    Developer = "Developer"


class LLMProvider(ExtendedStrEnum):
    "Represents provider"

    openai = "openai"
    bedrock = "bedrock"
    azure_openai = "azure_openai"
    azure_foundry = "azure_foundry"
    perplexity_ai = "perplexity_ai"
    anthropic_ai = "anthropic_ai"
    gemini_ai = "gemini_ai"
    lite_llm = "lite_llm"


class LiteLLMModels(ExtendedStrEnum):
    "Represents lite llm models"

    gpt_4o = "gpt-4o"
    gpt_4o_mini = "gpt-4o-mini"
    bedrock_anthropic_claude_sonnet = "bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0"
    gemini_flash = "gemini/gemini-2.0-flash"


class LangfusePrompt(ExtendedStrEnum):
    "Represents llm prompts"

    search_eval = "search_eval"
    search_eval_compare = "search_eval_compare"
    global_search = "global_search"
    generator = "generator"
    sql_agent = "sql_agent"
    mongo_agent = "mongo_agent"


class DatabaseType(ExtendedStrEnum):
    "Represents different database types"

    postgresql = "postgresql"
    pinecone = "pinecone"
    azure_ai_search = "azure_ai_search"
    chroma = "chroma"


class VectorDBModel(ExtendedStrEnum):
    pinecone = "pinecone"
    azure_ai_search = "azure_ai_search"


# endregion
