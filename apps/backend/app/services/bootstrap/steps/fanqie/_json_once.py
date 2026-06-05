"""番茄步骤复用通用 ``json_once``（兼容旧 import 路径）。"""

from app.services.bootstrap.json_once import (
    BootstrapStepError as FanqieStepError,
    call_bootstrap_json_once as call_fanqie_json_once,
)

__all__ = ["FanqieStepError", "call_fanqie_json_once"]
