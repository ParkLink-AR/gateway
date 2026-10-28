import sys

from pydantic import ConfigDict, model_validator
from pydantic_settings import BaseSettings


INSECURE_SECRET_SUBSTRINGS = ["dev-secret", "change-me", "reemplazar", "secret123", "password", "123456"]


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"

    # Base URLs of the microservices this gateway fronts. Empty string means
    # "not deployed yet" (e.g. booking-service) -> the gateway answers 503
    # instead of trying to connect.
    AUTH_SERVICE_URL: str = "http://auth-service:8000"
    PARKING_SERVICE_URL: str = "http://parking-service:3001"
    PAYMENT_SERVICE_URL: str = "http://payment-service:8004"
    BOOKING_SERVICE_URL: str = "http://booking-service:8080"
    NOTIFICATIONS_SERVICE_URL: str = "http://notifications-service:8000"

    # Must match the JWT_SECRET/JWT_ALGORITHM auth-service signs access tokens
    # with, so the gateway can verify them without calling auth-service.
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"

    # Shared key to authenticate gateway-originating calls to downstream services
    GATEWAY_INTERNAL_SECRET: str = "dev-gateway-secret-change-me"

    RABBITMQ_URL: str = "amqp://guest:guest@rabbitmq:5672/"
    EVENTS_EXCHANGE: str = "parklink.events"

    CORS_ORIGINS: str = "*"
    UPSTREAM_TIMEOUT_SECONDS: float = 15.0

    model_config = ConfigDict(extra="ignore", env_file=".env", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.ENVIRONMENT.lower() == "production":
            val = self.JWT_SECRET.lower()
            if len(self.JWT_SECRET) < 32 or any(s in val for s in INSECURE_SECRET_SUBSTRINGS):
                raise ValueError(
                    "FATAL: Insecure or default JWT_SECRET configured in production environment."
                )
            gateway_secret = self.GATEWAY_INTERNAL_SECRET.lower()
            if len(self.GATEWAY_INTERNAL_SECRET) < 32 or any(s in gateway_secret for s in INSECURE_SECRET_SUBSTRINGS):
                raise ValueError(
                    "FATAL: Insecure or default GATEWAY_INTERNAL_SECRET configured in production environment."
                )
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


# Tests must not pick up the developer's real .env (real secrets).
settings = Settings(_env_file=None if "pytest" in sys.modules else ".env")
