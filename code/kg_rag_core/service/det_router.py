# -*- coding: utf-8 -*-

# 该文件承载 deterministic 组合层：对外保留 ServiceDeterministicMixin，内部按主题拆分到多个子模块。

from .det_process import DeterministicProcessStepMixin
from .det_extreme import DeterministicGlobalExtremeMixin
from .det_effects import DeterministicEffectsMixin
from .det_controls import DeterministicControlsMixin
from .det_causes import DeterministicCausesMixin


class ServiceDeterministicMixin(
    DeterministicProcessStepMixin,
    DeterministicGlobalExtremeMixin,
    DeterministicEffectsMixin,
    DeterministicControlsMixin,
    DeterministicCausesMixin,
):
    """Compose all deterministic QA capabilities while preserving original class name."""

    pass
