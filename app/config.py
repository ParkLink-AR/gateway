from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"

    # Base URLs of the microservices this gateway fronts. Empty string means
    # "not deployed yet" (e.g. booking-service) -> the gateway answers 503
    # instead of trying to connect.
    AUTH_SERVICE_URL: str = "http://auth-service:8000"
    PARKING_SERVICE_URL: str = "http://parking-service:3001"
    PAYMENT_SERVICE_URL: str = "http://payment-service:8004"
    BOOKING_SERVICE_URL: str = ""

    # Must match the JWT_SECRET/JWT_ALGORITHM auth-service signs access tokens
    # with, so the gateway can verify them without calling auth-service.
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"

    RABBITMQ_URL: str = "amqp://guest:guest@rabbitmq:5672/"
    EVENTS_EXCHANGE: str = "parklink.events"

    CORS_ORIGINS: str = "*"
    UPSTREAM_TIMEOUT_SECONDS: float = 15.0

    model_config = ConfigDict(extra="ignore", env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
