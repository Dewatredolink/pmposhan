from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PM POSHAN API"
    database_url: str = "postgresql+psycopg://pmposhan:pmposhan@localhost:5432/pmposhan"
    auth_required: bool = False
    # Public issuer is what the browser-visible Keycloak puts in the token `iss` claim.
    keycloak_issuer: str = "http://localhost:8080/realms/pmposhan"
    # Backend can fetch signing keys over Docker's internal network.
    keycloak_jwks_url: str = "http://localhost:8080/realms/pmposhan/protocol/openid-connect/certs"
    keycloak_web_client_id: str = "pmposhan-web"
    cors_origins: str = "http://localhost:5173"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
