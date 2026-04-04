from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Core DB (Primary — source of truth)
    CORE_DB_HOST: str = "core-db"
    CORE_DB_PORT: int = 5432
    CORE_DB_USER: str = "payment_admin"
    CORE_DB_PASSWORD: str = "payment_secret"
    CORE_DB_NAME: str = "payment_core"

    # Core DB Replica (read-only — for Bulk API + Analytics)
    CORE_DB_REPLICA_HOST: str = "core-db-replica"
    CORE_DB_REPLICA_PORT: int = 5432

    # Read DB (System 3 — internal only, for DB sync consumer)
    READ_DB_HOST: str = "read-db"
    READ_DB_PORT: int = 5432
    READ_DB_USER: str = "payment_admin"
    READ_DB_PASSWORD: str = "payment_secret"
    READ_DB_NAME: str = "payment_read"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Kafka
    KAFKA_BROKERS: str = "redpanda:9092"
    KAFKA_TOPIC: str = "payments.events"

    # OAuth / JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_SECONDS: int = 3600
    ADMIN_API_KEY: str = "change-me-in-production"

    # Third-party Webhooks
    TP_WEBHOOK_MAX_RETRIES: int = 6
    TP_WEBHOOK_TIMEOUT_SECONDS: int = 10
    TP_WEBHOOK_VERIFY_ON_CREATE: bool = True

    # Rate Limiting
    RATE_LIMIT_DEFAULT_REQUESTS: int = 1000
    RATE_LIMIT_DEFAULT_WINDOW_SECONDS: int = 300
    OAUTH_RATE_LIMIT_PER_MINUTE: int = 10

    # Service
    CONNECT_SERVICE_PORT: int = 8002
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174,http://localhost:5175"

    @property
    def read_db_dsn(self) -> str:
        """Read DB DSN — for DB sync consumer (System 3 internal)."""
        return f"postgresql://{self.READ_DB_USER}:{self.READ_DB_PASSWORD}@{self.READ_DB_HOST}:{self.READ_DB_PORT}/{self.READ_DB_NAME}"

    @property
    def core_db_dsn(self) -> str:
        """Core DB Primary DSN — for writes (consumer CRUD, webhooks, audit)."""
        return f"postgresql://{self.CORE_DB_USER}:{self.CORE_DB_PASSWORD}@{self.CORE_DB_HOST}:{self.CORE_DB_PORT}/{self.CORE_DB_NAME}"

    @property
    def core_replica_dsn(self) -> str:
        """Core DB Replica DSN — read-only (Bulk API, Analytics)."""
        return f"postgresql://{self.CORE_DB_USER}:{self.CORE_DB_PASSWORD}@{self.CORE_DB_REPLICA_HOST}:{self.CORE_DB_REPLICA_PORT}/{self.CORE_DB_NAME}"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
