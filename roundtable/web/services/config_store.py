"""
Managed config storage for secrets and product settings.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.structures import ProviderSecretState


PROVIDER_ENV_KEYS = {
    "gemini": "GEMINI_API_KEY",
    "claude": "CLAUDE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "volcengine": "VOLCENGINE_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    "dashscope_coding": "DASHSCOPE_CODING_API_KEY",
}

DEFAULT_SETTINGS = {
    "enabled_models": {
        "gemini-2.5-flash": True,
        "openrouter/deepseek/deepseek-chat-v3-0324:free": True,
        "qwen3.5-plus": True,
    },
    "role_template_defaults": {},
    "ui_defaults": {},
}


class ConfigStore:
    """Persist secrets in .env and product settings in settings.json."""

    def __init__(
        self,
        env_path: Optional[str] = None,
        settings_path: Optional[str] = None,
    ):
        project_root = Path(__file__).resolve().parents[2]
        self.env_path = Path(env_path) if env_path else project_root / ".env"
        self.settings_path = (
            Path(settings_path) if settings_path else project_root / "data" / "settings.json"
        )
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)

    def get_env_key_for_provider(self, provider: str) -> str:
        """Map provider id to .env key."""
        if provider not in PROVIDER_ENV_KEYS:
            raise ValueError(f"Unsupported provider: {provider}")
        return PROVIDER_ENV_KEYS[provider]

    def get_secret(self, env_key: str) -> Optional[str]:
        """Read one secret from os.environ or managed .env."""
        env_override = os.getenv(env_key)
        if env_override:
            return env_override

        values = self._read_env_map()
        value = values.get(env_key)
        return str(value) if value else None

    def set_provider_secret(self, provider: str, api_key: str) -> ProviderSecretState:
        """Save or clear a provider secret."""
        env_key = self.get_env_key_for_provider(provider)
        env_map = self._read_env_map()

        normalized = api_key.strip()
        if normalized:
            env_map[env_key] = normalized
            os.environ[env_key] = normalized
        else:
            env_map.pop(env_key, None)
            os.environ.pop(env_key, None)

        self._write_env_map(env_map)
        return self.get_provider_state(provider)

    def get_provider_state(self, provider: str) -> ProviderSecretState:
        """Return masked provider secret state for UI display."""
        env_key = self.get_env_key_for_provider(provider)
        secret = self.get_secret(env_key)
        return ProviderSecretState(
            provider=provider,
            configured=bool(secret),
            masked_value=self.mask_secret(secret),
            connection_status="unknown",
        )

    def list_provider_states(self) -> List[ProviderSecretState]:
        """List every supported provider state."""
        return [self.get_provider_state(provider) for provider in PROVIDER_ENV_KEYS]

    def load_settings(self) -> Dict[str, Any]:
        """Load settings.json with defaults merged in."""
        payload = self._deep_copy(DEFAULT_SETTINGS)
        if self.settings_path.exists():
            with open(self.settings_path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            payload = self._merge_dicts(payload, stored)
        return payload

    def save_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Persist settings.json atomically."""
        merged = self._merge_dicts(self._deep_copy(DEFAULT_SETTINGS), settings)
        temp_path = self.settings_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(merged, handle, ensure_ascii=False, indent=2)
        temp_path.replace(self.settings_path)
        return merged

    def update_enabled_models(self, enabled_models: Dict[str, bool]) -> Dict[str, Any]:
        """Update enabled model map."""
        settings = self.load_settings()
        settings["enabled_models"] = dict(enabled_models)
        return self.save_settings(settings)

    @staticmethod
    def mask_secret(value: Optional[str]) -> str:
        """Return a masked display string."""
        if not value:
            return ""
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}****{value[-4:]}"

    def _read_env_map(self) -> Dict[str, str]:
        if not self.env_path.exists():
            return {}

        values: Dict[str, str] = {}
        for raw_line in self.env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    def _write_env_map(self, env_map: Dict[str, str]) -> None:
        lines = [f"{key}={value}" for key, value in sorted(env_map.items())]
        content = "\n".join(lines)
        if content:
            content += "\n"
        temp_path = self.env_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(self.env_path)

    def _merge_dicts(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        merged = self._deep_copy(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._merge_dicts(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _deep_copy(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return json.loads(json.dumps(payload))
