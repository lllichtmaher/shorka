from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    elevenlabs_api_key: str = ""
    groq_api_key: str = ""

    stt_provider: str = "openai"
    stt_model: str = "gpt-4o-mini-transcribe"

    claude_model: str = "claude-sonnet-4-6"
    claude_max_tokens: int = 1024

    elevenlabs_model: str = "eleven_flash_v2_5"
    elevenlabs_output_format: str = "pcm_24000"
    elevenlabs_stability: float = 0.5
    elevenlabs_similarity_boost: float = 0.8

    sample_rate_in: int = 16000
    sample_rate_out: int = 24000
    vad_threshold: float = 0.8
    vad_min_silence_ms: int = 500
    min_utterance_ms: int = 600

    voices_path: Path = Path(__file__).parent.parent / "data" / "voices.json"
    apps_index_path: Path = Path.home() / ".voicectl" / "apps.json"


settings = Settings()
