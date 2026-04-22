from __future__ import annotations

"""运行装配辅助。

用于复用 run/test 入口中的组件初始化逻辑，避免多处复制粘贴。
"""

from pathlib import Path

from config import voice as voice_config
from sylphos.runtime.events import EventBus
from sylphos.runtime.orchestrator import RuntimeOrchestrator
from voice.audio.event_bridge import RecorderEventBridge
from voice.audio.hub import AudioHub
from voice.audio.recorder import CommandRecorder
from voice.wakeword.openwakeword_engine import OpenWakeWordEngine


def choose_device_from_config() -> int | str | None:
    """优先按设备名匹配，未配置时回退到设备索引。"""
    if voice_config.AUDIO_INPUT_DEVICE_NAME:
        return voice_config.AUDIO_INPUT_DEVICE_NAME
    return voice_config.AUDIO_INPUT_DEVICE_INDEX


def resolve_wakeword_model_path() -> Path | None:
    """按当前配置解析模型路径，仅用于配置自检和信息展示。"""
    source = voice_config.WAKEWORD_MODEL_SOURCE

    if source == "openwakeword_resource":
        if not voice_config.WAKEWORD_MODEL_NAME:
            return None
        import importlib.resources as ir

        model_dir = Path(str(ir.files("openwakeword") / "resources" / "models"))
        return model_dir / voice_config.WAKEWORD_MODEL_NAME

    if source == "project_relative":
        if not voice_config.WAKEWORD_MODEL_RELATIVE_PATH:
            return None
        model_path = Path(voice_config.WAKEWORD_MODEL_RELATIVE_PATH)
        if not model_path.is_absolute():
            model_path = Path.cwd() / model_path
        return model_path

    return None


def create_runtime_stack() -> dict[str, object]:
    """创建完整运行链路所需组件。"""
    event_bus = EventBus()

    hub = AudioHub(
        device=choose_device_from_config(),
        samplerate=voice_config.INPUT_RATE,
        channels=voice_config.CHANNELS,
        blocksize=voice_config.BLOCKSIZE,
        dtype=voice_config.DTYPE,
    )

    recorder = CommandRecorder(
        input_rate=voice_config.INPUT_RATE,
        save_dir=voice_config.RECORDINGS_DIR,
        save_mode=voice_config.RECORD_SAVE_MODE,
        latest_filename=voice_config.LATEST_RECORD_FILENAME,
        vad_enabled=voice_config.VAD_ENABLED,
        vad_sample_rate=voice_config.VAD_SAMPLE_RATE,
        vad_threshold=voice_config.VAD_THRESHOLD,
        vad_min_speech_duration_ms=voice_config.VAD_MIN_SPEECH_DURATION_MS,
        vad_min_silence_duration_ms=voice_config.VAD_MIN_SILENCE_DURATION_MS,
        vad_speech_pad_ms=voice_config.VAD_SPEECH_PAD_MS,
        vad_end_silence_ms=voice_config.VAD_END_SILENCE_MS,
        vad_prebuffer_ms=voice_config.VAD_PREBUFFER_MS,
        vad_check_interval_ms=voice_config.VAD_CHECK_INTERVAL_MS,
    )

    wake = OpenWakeWordEngine(
        input_rate=voice_config.INPUT_RATE,
        target_rate=16000,
        threshold=voice_config.WAKEWORD_THRESHOLD,
        cooldown_seconds=voice_config.WAKEWORD_COOLDOWN_SECONDS,
        wakeword_model_source=voice_config.WAKEWORD_MODEL_SOURCE,
        wakeword_model_name=voice_config.WAKEWORD_MODEL_NAME,
        wakeword_model_relative_path=voice_config.WAKEWORD_MODEL_RELATIVE_PATH,
    )

    orchestrator = RuntimeOrchestrator(
        event_bus=event_bus,
        wakeword_engine=wake,
        record_seconds=voice_config.COMMAND_RECORD_SECONDS,
    )

    recorder_bridge = RecorderEventBridge(event_bus=event_bus, recorder=recorder)

    hub.subscribe(wake.consume)
    hub.subscribe(recorder.consume)

    return {
        "event_bus": event_bus,
        "hub": hub,
        "recorder": recorder,
        "wake": wake,
        "orchestrator": orchestrator,
        "recorder_bridge": recorder_bridge,
    }


def start_runtime_stack(stack: dict[str, object]) -> None:
    """按顺序启动组件。"""
    stack["orchestrator"].start()
    stack["recorder_bridge"].start()
    stack["hub"].start()


def stop_runtime_stack(stack: dict[str, object]) -> None:
    """按逆序停止组件。"""
    stack["hub"].stop()
    stack["recorder_bridge"].stop()
    stack["orchestrator"].stop()
    stack["recorder"].close()
    stack["wake"].close()
