from ..core.capability_model import BackendCapabilities
from .office_backend import OfficeBackend


class PowerPointCOMBackend(OfficeBackend):
    kind = "powerpoint"
    label = "Microsoft PowerPoint"

    def get_capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            video=True,
            video_controls=True,
            audio=True,
            animations=True,
            transitions=True,
            native_window=True,
            animation_steps=True,
        )
