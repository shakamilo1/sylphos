from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass

try:
    from rich.logging import RichHandler
    _HAS_RICH = True
except Exception:
    _HAS_RICH = False

from sylphos.config.loader import load_config
from sylphos.executor.openclaw_config import load_openclaw_bridge_config
from sylphos.executor.openclaw_executor import DummyExecutor, OpenClawApiExecutor, OpenClawCliExecutor, OpenClawExecutor, OpenClawWebSocketExecutor
from sylphos.frontend.console_feedback import ConsoleFeedback
from sylphos.runtime.context import RuntimeContext
from sylphos.runtime.event_bus import EventBus
from sylphos.runtime.orchestrator import RuntimeOrchestrator, SimpleRouter
from sylphos.runtime.registry import RuntimeRegistry
from sylphos.runtime.stt_handler import STTHandler
from sylphos.runtime.tts_handler import TTSHandler
from sylphos.voice.audio.hub import AudioHubAdapter
from sylphos.voice.audio.recorder import RecorderService
from sylphos.voice.stt import DummySTT, SenseVoiceRuntimeAdapter, build_post_processors
from sylphos.voice.tts import CosyVoiceClient, DummyTTS
from sylphos.voice.wakeword.openwakeword_engine import OpenWakeWordEngineAdapter


def configure_logging(level: int = logging.INFO) -> None:
    if _HAS_RICH:
        logging.basicConfig(level=level, format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True)])
    else:
        logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class RuntimeApp:
    def __init__(self, config=None) -> None:
        self.config = config or load_config()
        self.event_bus = EventBus()
        self.context = RuntimeContext()
        self.registry = RuntimeRegistry()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.orchestrator = None

    def build(self) -> "RuntimeApp":
        audio = self.registry.register("audio_hub", AudioHubAdapter(
            enabled=bool(getattr(self.config, "AUDIO_ENABLED", False)),
            device=getattr(self.config, "AUDIO_DEVICE", None),
            samplerate=int(getattr(self.config, "AUDIO_SAMPLE_RATE", 44100)),
            channels=int(getattr(self.config, "AUDIO_CHANNELS", 1)),
            blocksize=int(getattr(self.config, "AUDIO_BLOCKSIZE", 4410)),
        ))
        self.registry.register("wakeword", OpenWakeWordEngineAdapter(self.event_bus, audio_hub=audio, enabled=bool(getattr(self.config, "AUDIO_ENABLED", False))))
        self.registry.register("recorder", RecorderService(self.event_bus, audio_hub=audio, samplerate=int(getattr(self.config, "AUDIO_SAMPLE_RATE", 44100))))

        stt_provider = getattr(self.config, "STT_PROVIDER", "dummy")
        stt_engine = DummySTT(getattr(self.config, "DUMMY_STT_TEXT", "打开浏览器")) if stt_provider == "dummy" else SenseVoiceRuntimeAdapter(provider=stt_provider)
        self.registry.register("stt", STTHandler(event_bus=self.event_bus, context=self.context, engine=stt_engine))

        tts_provider = getattr(self.config, "TTS_PROVIDER", "dummy")
        tts_engine = DummyTTS() if tts_provider == "dummy" else CosyVoiceClient(base_url=getattr(self.config, "COSYVOICE_URL", "http://127.0.0.1:8000"))
        self.registry.register("tts", TTSHandler(event_bus=self.event_bus, engine=tts_engine))

        self.registry.register_executor("dummy", DummyExecutor())
        openclaw_config = load_openclaw_bridge_config()
        self.registry.register_executor("openclaw", OpenClawExecutor(config=openclaw_config))
        self.registry.register_executor("openclaw_cli", OpenClawCliExecutor(config=openclaw_config))
        self.registry.register_executor("openclaw_api", OpenClawApiExecutor(config=openclaw_config))
        self.registry.register_executor("openclaw_websocket", OpenClawWebSocketExecutor(config=openclaw_config))
        self.registry.register("console_feedback", ConsoleFeedback(self.event_bus))
        self.orchestrator = self.registry.register("orchestrator", RuntimeOrchestrator(
            event_bus=self.event_bus,
            context=self.context,
            registry=self.registry,
            config=self.config,
            post_processors=build_post_processors(self.config),
            router=SimpleRouter(default_tool=getattr(self.config, "TOOL_EXECUTOR_PROVIDER", "dummy")),
        ))
        return self

    def start(self) -> None:
        if self.orchestrator is None:
            self.build()
        for name, module in list(self.registry.modules.items()):
            if name == "audio_hub":
                continue
            start = getattr(module, "start", None)
            if callable(start):
                self.logger.info("starting module=%s", name)
                start()
        audio = self.registry.get("audio_hub")
        if audio is not None:
            audio.start()

    def close(self) -> None:
        self.registry.close_all()
        self.logger.info("Runtime closed")

    def context_snapshot(self) -> dict:
        data = asdict(self.context) if is_dataclass(self.context) else vars(self.context)
        data["state"] = str(self.context.state)
        data["last_event"] = self.context.last_event.event_type if self.context.last_event else None
        return data
