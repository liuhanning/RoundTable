import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import (  # noqa: E402
    get_config_store,
    get_model_config,
    reload_config,
    reset_config_cache,
    set_config_paths,
    validate_api_keys,
)
from web.services.config_store import ConfigStore  # noqa: E402


class TestConfigStore:
    def test_set_provider_secret_writes_env_and_masks_value(self, tmp_path):
        store = ConfigStore(
            env_path=str(tmp_path / ".env"),
            settings_path=str(tmp_path / "settings.json"),
        )

        state = store.set_provider_secret("gemini", "sk-test-12345678")

        assert state.provider == "gemini"
        assert state.configured is True
        assert state.masked_value == "sk-t****5678"
        assert "GEMINI_API_KEY=sk-test-12345678" in (tmp_path / ".env").read_text(encoding="utf-8")

    def test_clear_secret_only_removes_target_provider(self, tmp_path):
        store = ConfigStore(
            env_path=str(tmp_path / ".env"),
            settings_path=str(tmp_path / "settings.json"),
        )
        store.set_provider_secret("gemini", "gem-key")
        store.set_provider_secret("openrouter", "or-key")

        store.set_provider_secret("gemini", "")
        env_content = (tmp_path / ".env").read_text(encoding="utf-8")

        assert "GEMINI_API_KEY" not in env_content
        assert "OPENROUTER_API_KEY=or-key" in env_content

    def test_settings_are_saved_with_defaults_merged(self, tmp_path):
        store = ConfigStore(
            env_path=str(tmp_path / ".env"),
            settings_path=str(tmp_path / "settings.json"),
        )

        saved = store.save_settings(
            {
                "enabled_models": {"gemini-2.5-flash": False},
                "ui_defaults": {"landing_page": "/settings"},
            }
        )

        assert saved["enabled_models"]["gemini-2.5-flash"] is False
        assert "role_template_defaults" in saved
        assert saved["ui_defaults"]["landing_page"] == "/settings"


class TestConfigModule:
    def teardown_method(self):
        for key in [
            "GEMINI_API_KEY",
            "OPENROUTER_API_KEY",
            "CLAUDE_API_KEY",
            "VOLCENGINE_API_KEY",
            "DASHSCOPE_API_KEY",
            "DASHSCOPE_CODING_API_KEY",
        ]:
            os.environ.pop(key, None)
        set_config_paths()
        reset_config_cache()

    def test_reload_config_reads_managed_env_file(self, tmp_path):
        env_path = tmp_path / ".env"
        settings_path = tmp_path / "settings.json"
        env_path.write_text("GEMINI_API_KEY=file-key\n", encoding="utf-8")

        set_config_paths(str(env_path), str(settings_path))
        reload_config()
        model_config = get_model_config()

        assert model_config.GEMINI_API_KEY == "file-key"
        assert validate_api_keys() is True

    def test_process_env_overrides_managed_env(self, tmp_path, monkeypatch):
        env_path = tmp_path / ".env"
        settings_path = tmp_path / "settings.json"
        env_path.write_text("GEMINI_API_KEY=file-key\n", encoding="utf-8")
        monkeypatch.setenv("GEMINI_API_KEY", "env-key")

        set_config_paths(str(env_path), str(settings_path))
        model_config = get_model_config()

        assert model_config.GEMINI_API_KEY == "env-key"

    def test_get_config_store_uses_overridden_paths(self, tmp_path):
        env_path = tmp_path / ".env"
        settings_path = tmp_path / "settings.json"

        set_config_paths(str(env_path), str(settings_path))
        store = get_config_store()

        assert store.env_path == env_path
        assert store.settings_path == settings_path
