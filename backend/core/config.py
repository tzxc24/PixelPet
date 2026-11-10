"""Resolve local configuration independently of the shell's working directory."""
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import dotenv_values
from backend.access import parse_allowed_hosts

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PIXELPET_", env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )
    database_path: Path = Path("output/pixelpet.sqlite3")
    llm_base_url: str = Field(default="", validation_alias="LLM_BASE_URL")
    llm_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="LLM_API_KEY")
    llm_model: str = Field(default="", validation_alias="LLM_MODEL")
    llm_timeout: float = Field(default=45, gt=0, le=300, validation_alias="LLM_TIMEOUT")
    llm_history_max_chars: int = Field(default=500000, ge=1000, le=5000000, validation_alias="LLM_HISTORY_MAX_CHARS")
    llm_mode: Literal["auto", "mock", "openai"] = Field(default="auto", validation_alias="LLM_MODE")
    llm_provider: Literal["openai", "deepseek"] = Field(default="openai", validation_alias="LLM_PROVIDER")
    deepseek_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="DEEPSEEK_API_KEY")
    llm_thinking: Literal["disabled", "enabled"] = Field(default="disabled", validation_alias="LLM_THINKING")
    baidu_asr_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="BAIDU_ASR_API_KEY")
    baidu_asr_secret_key: SecretStr = Field(default=SecretStr(""), validation_alias="BAIDU_ASR_SECRET_KEY")
    baidu_asr_timeout: float = Field(default=20, gt=0, le=60, validation_alias="BAIDU_ASR_TIMEOUT")
    baidu_asr_dev_pid: int = Field(default=1537, gt=0, validation_alias="BAIDU_ASR_DEV_PID")
    character_path: Path = Path("config/character.json")
    asr_model: str = "base"
    asr_model_download: bool = False
    memory_decay_days: float = Field(default=90,ge=0,le=3650)
    speech_timeout: float = Field(default=120,gt=0,le=300)
    access_token: SecretStr = SecretStr("")
    allowed_hosts: str = 'localhost,127.0.0.1,::1'

    @field_validator('allowed_hosts')
    @classmethod
    def explicit_hosts(cls, value):
        parse_allowed_hosts(value)
        return value

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        # Explicit python-dotenv parsing without modifying process environment.
        def local_file():
            values=dotenv_values(ROOT / ".env",encoding="utf-8-sig",interpolate=False)
            known={"LLM_HISTORY_MAX_CHARS","BAIDU_ASR_API_KEY","BAIDU_ASR_SECRET_KEY","BAIDU_ASR_TIMEOUT","BAIDU_ASR_DEV_PID","LLM_PROVIDER","LLM_BASE_URL","LLM_API_KEY","LLM_MODEL","LLM_TIMEOUT","LLM_MODE","LLM_THINKING","DEEPSEEK_API_KEY"}
            result={key:value for key,value in values.items() if key in known and value is not None}
            for key in ("database_path","character_path","asr_model","asr_model_download","memory_decay_days","speech_timeout","access_token","allowed_hosts"):
                value=values.get("PIXELPET_"+key.upper())
                if value is not None:
                    result[key]=value
            return result
        return init_settings,env_settings,local_file,file_secret_settings

    def resolved_database_path(self) -> Path:
        path = self.database_path.expanduser()
        return path if path.is_absolute() else ROOT / path
