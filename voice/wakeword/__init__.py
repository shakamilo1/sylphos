"""唤醒词引擎层。"""

from voice.wakeword.base import WakeWordEngine
from voice.wakeword.openwakeword_engine import OpenWakeWordEngine

__all__ = ["WakeWordEngine", "OpenWakeWordEngine"]
