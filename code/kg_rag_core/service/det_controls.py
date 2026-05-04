# -*- coding: utf-8 -*-

# 该文件承载 controls 组合层：对外保留 DeterministicControlsMixin，内部按功能拆分。

from .det_ctrl_lookup import DeterministicControlsLookupMixin
from .det_ctrl_presence import DeterministicControlsPresenceMixin
from .det_ctrl_types import DeterministicControlsTypesMixin


class DeterministicControlsMixin(
    DeterministicControlsLookupMixin,
    DeterministicControlsPresenceMixin,
    DeterministicControlsTypesMixin,
):
    """Compose all control-related deterministic QA capabilities."""

    pass
