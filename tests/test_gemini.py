import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Provide stub google modules if they are missing to avoid heavy dependencies
for mod in [
    "google",
    "google.generativeai",
    "google.api_core",
    "google.api_core.exceptions",
    "google.auth",
    "google.auth.exceptions",
    "google.cloud",
    "google.cloud.aiplatform",
    "vertexai",
    "vertexai.preview",
    "vertexai.preview.generative_models",
    "vertexai.preview.language_models",
    "numpy",
]:
    sys.modules.setdefault(mod, MagicMock())

# Minimal YAML stub to satisfy configuration loading
if "yaml" not in sys.modules:
    yaml_stub = ModuleType("yaml")
    DEFAULT_CONFIG = {
        "instances": {
            "jo": {
                "name": "Jo HR Assistant",
                "supports_noi": True,
                "hr_support_url": "https://hrsupport.usclarity.com/support/home",
                "hostname_patterns": ["hr-chatbot-jo-*", "*-jo-*"],
                "default": True,
            }
        },
        "global_settings": {"data_base_dir": "data", "auto_create_directories": True},
    }
    yaml_stub.safe_load = lambda f: DEFAULT_CONFIG
    yaml_stub.dump = lambda data, stream=None, **kwargs: None
    sys.modules["yaml"] = yaml_stub

# Provide a lightweight settings object used by services
if "hrbot.config.settings" not in sys.modules:
    settings_stub = SimpleNamespace(
        gemini=SimpleNamespace(
            model_name="test-model",
            temperature=0.2,
            max_output_tokens=256,
            api_key="",
            use_aws_secrets=False,
        ),
        google_cloud=SimpleNamespace(project_id="proj", location="us-central1"),
        performance=SimpleNamespace(cache_embeddings=False, cache_ttl_seconds=0),
    )
    settings_mod = ModuleType("hrbot.config.settings")
    settings_mod.settings = settings_stub
    sys.modules["hrbot.config.settings"] = settings_mod

# Add the src directory so tests can import the package
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from hrbot.utils.result import Success


@pytest.mark.asyncio
async def test_gemini_service_connection(monkeypatch):
    from hrbot.services.gemini_service import GeminiService

    async def fake_analyze_messages(self, messages):
        return Success({"response": "pong"})

    monkeypatch.setattr(GeminiService, "analyze_messages", fake_analyze_messages)
    service = GeminiService()
    assert await service.test_connection() is True


@pytest.mark.asyncio
async def test_chat_processor_success(monkeypatch):
    from hrbot.services.gemini_service import GeminiService
    from hrbot.services.processor import ChatProcessor
    from hrbot.utils import di

    service = GeminiService()
    monkeypatch.setattr(di, "get_vector_store", lambda: MagicMock())
    processor = ChatProcessor(service)

    async def fake_query(*args, **kwargs):
        return Success({"response": "ok", "confidence_level": "high"})

    monkeypatch.setattr(processor.rag, "query", fake_query)

    result = await processor.process_message(
        "Tell me about the benefits of exercise",
        chat_history=["I want to learn about healthy habits"],
    )

    assert result.is_success()
