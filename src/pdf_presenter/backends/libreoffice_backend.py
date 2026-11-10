from ..core.capability_model import BackendCapabilities
from .office_backend import OfficeBackend


class LibreOfficeFallbackBackend(OfficeBackend):
    kind = "libreoffice"
    label = "LibreOffice Impress"

    def get_capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            video=True,
            audio=True,
            animations=True,
            transitions=True,
            native_window=True,
            animation_steps=True,
            compatibility=True,
        )
