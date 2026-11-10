from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from pdf_presenter.i18n import tr

from ..core.media_layout import media_rect
from ..core.render_service import Raster
from .icons import icon


def raster_image(raster: Raster) -> QImage:
    return QImage(
        raster.samples, raster.width, raster.height, raster.stride, QImage.Format.Format_RGB888
    ).copy()


class SlideWidget(QWidget):
    resized = Signal()
    panned = Signal(float, float)

    def __init__(self, audience: bool = False) -> None:
        super().__init__()
        self.audience = audience
        self.page = -1
        self.image = QImage()
        self.blank = ""
        self.message = tr("Добавьте презентацию, изображение или видео")
        self.view_source = None
        self.view_settings = {}
        self.reference_size = None
        self._drag = None
        self.setMinimumSize(100, 70)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName(tr("Слайд аудитории") if audience else tr("Предпросмотр слайда"))

    def prepare(self, page: int, message: str = tr("Загрузка слайда…")) -> None:
        if self.page != page:
            self.image = QImage()
        self.page, self.message = page, message
        self.update()

    def set_raster(self, page: int, raster: Raster) -> None:
        if page == self.page:
            self.image = raster_image(raster)
            self.update()

    def set_blank(self, color: str) -> None:
        self.blank = color
        self.update()

    def render_size(self) -> tuple[int, int]:
        ratio = self.devicePixelRatioF()
        return max(16, int(self.width() * ratio)), max(16, int(self.height() * ratio))

    def set_media_view(self, source=None, settings=None, reference_size=None) -> None:
        self.view_source = source
        self.view_settings = dict(settings or {})
        self.reference_size = reference_size
        self.setToolTip(
            tr("Перетащите увеличенное изображение для выбора видимой области")
            if source and not self.audience
            else ""
        )
        self.update()

    def content_rects(self):
        """Map the audience's pixel viewport into this preview, including its crop."""
        width, height = self.reference_size or self.render_size()
        factor = min(self.width() / width, self.height() / height)
        viewport = QRectF(
            (self.width() - width * factor) / 2,
            (self.height() - height * factor) / 2,
            width * factor,
            height * factor,
        )
        target = media_rect(QRectF(0, 0, width, height), self.view_source, self.view_settings)
        return viewport, QRectF(
            viewport.x() + target.x() * factor,
            viewport.y() + target.y() * factor,
            target.width() * factor,
            target.height() * factor,
        )

    def mousePressEvent(self, event):
        if self.view_source and not self.audience and event.button() == Qt.MouseButton.LeftButton:
            self._drag = (event.position(), dict(self.view_settings))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag is None:
            return super().mouseMoveEvent(event)
        origin, settings = self._drag
        viewport, target = self.content_rects()
        delta = event.position() - origin
        pan = []
        for key, movement, excess in (
            ("pan_x", delta.x(), target.width() - viewport.width()),
            ("pan_y", delta.y(), target.height() - viewport.height()),
        ):
            pan.append(
                max(-1, min(1, settings.get(key, 0) - 2 * movement / excess)) if excess > 1 else 0
            )
        self.view_settings.update(pan_x=pan[0], pan_y=pan[1])
        self.panned.emit(*pan)
        self.update()

    def mouseReleaseEvent(self, event):
        self._drag = None
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        self.resized.emit()

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(
            self.rect(), QColor(self.blank or ("black" if self.audience else "#10141C"))
        )
        if self.blank:
            return
        if not self.image.isNull():
            if self.view_source:
                viewport, target = self.content_rects()
                painter.fillRect(viewport, QColor("black"))
                painter.setClipRect(viewport)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                painter.drawImage(target, self.image)
                return
            size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRectF(
                (self.width() - size.width()) / 2,
                (self.height() - size.height()) / 2,
                size.width(),
                size.height(),
            )
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(target, self.image)
        elif not self.audience:
            if self.page < 0 and self.message == tr("Добавьте презентацию, изображение или видео"):
                center = self.rect().center()
                painter.drawPixmap(
                    center.x() - 24, center.y() - 80, icon("screen", "#AB96F4").pixmap(48, 48)
                )
                font = painter.font()
                font.setPixelSize(21)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor("#E3E9F7"))
                painter.drawText(
                    QRectF(20, center.y() - 10, self.width() - 40, 35),
                    Qt.AlignmentFlag.AlignCenter,
                    tr("Подготовьте свою сцену"),
                )
                font.setPixelSize(13)
                font.setBold(False)
                painter.setFont(font)
                painter.setPen(QColor("#9AA8BF"))
                painter.drawText(
                    QRectF(20, center.y() + 30, self.width() - 40, 65),
                    Qt.AlignmentFlag.AlignHCenter
                    | Qt.AlignmentFlag.AlignTop
                    | Qt.TextFlag.TextWordWrap,
                    tr(
                        "Добавьте презентации, изображения или видео.\nФайлы можно перетащить прямо в окно."
                    ),
                )
                return
            painter.setPen(QColor("#94A3B8"))
            painter.drawText(
                self.rect().adjusted(20, 15, -20, -15),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self.message,
            )
