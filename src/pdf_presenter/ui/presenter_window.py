from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pdf_presenter.i18n import LANGUAGES, language, tr

from ..backends.pdf_backend import PDFBackend
from ..core.audience_display_manager import AudienceDisplayManager, AudienceMode
from ..core.backend_manager import BackendManager
from ..core.canva_url import is_canva_url, normalize_canva_url
from ..core.capability_model import PresentationDocument
from ..core.display_handoff import DisplayHandoffCoordinator
from ..core.media_formats import file_filter
from ..core.monitor_manager import MonitorManager
from ..core.notes_manager import NotesManager
from ..core.presentation_controller import PresentationController
from ..core.presentation_queue import PresentationQueueManager, QueueState
from ..core.presentation_timer import PresentationTimer
from ..core.project_manager import EventProject, ProjectManager
from ..core.render_service import Raster
from ..core.settings_manager import SettingsManager
from ..core.slide_controller import SlideController
from ..core.storage import StorageError
from ..services.native_input import NativeInputRouter
from ..services.presentation_preloader import PresentationPreloader
from .audience_window import AudienceWindow
from .backend_status_widget import BackendStatusWidget
from .elided_label import ElidedLabel
from .icons import icon
from .keyboard_router import KeyboardRouter
from .media_warning_dialog import MediaWarningDialog
from .navigation_panel import NavigationPanel
from .notes_panel import NotesPanel
from .preflight_dialog import PreflightDialog
from .presentation_queue_panel import PresentationQueuePanel
from .slide_widget import SlideWidget
from .thumbnail_panel import ThumbnailPanel

log = logging.getLogger(__name__)


class PresenterWindow(QMainWindow):
    def __init__(self, data_root: Path | None = None) -> None:
        super().__init__()
        self.data_root = data_root
        self.settings = SettingsManager(data_root)
        self.document: PresentationDocument | None = None
        self.notes: NotesManager | None = None
        self.loading = False
        self._loading_path = ""
        self._closing = False
        self._screen_connected = False
        self._notes_error_shown = False
        self.slides = SlideController()
        self.timer = PresentationTimer()
        self.presentation = PresentationController(self.slides, self.timer)
        self.renderer = PDFBackend(self)
        self.backend_manager = BackendManager()
        self.queue = PresentationQueueManager(self)
        self.project_manager = ProjectManager()
        self.project = EventProject()
        self.preloader = PresentationPreloader(self.backend_manager, self.queue, self)
        self._pending_item = ""
        self._switch_candidate = None
        self._preflight_ids = []
        self._preflight_running = False
        self._preflight_dialog = None
        self._project_dirty = False
        self._close_waiting = False
        self.monitors = MonitorManager(self)
        self.audience = AudienceWindow()
        self.audience_display = AudienceDisplayManager(self.audience, self.monitors, self, self)
        self.handoff = DisplayHandoffCoordinator(self.audience_display, self)
        self.setWindowTitle(tr("Сцена"))
        self.setWindowIcon(QIcon(str(Path(__file__).parents[1] / "resources/icons/scene.ico")))
        self.resize(1440, 900)
        self.setMinimumSize(900, 650)
        self.setAcceptDrops(True)
        self._build_ui()
        self._build_menu()
        self._connect()
        self._restore_settings()
        self._refresh_monitors()
        self.keyboard = KeyboardRouter(self)
        self.native_input = NativeInputRouter(self)
        self.native_input.command.connect(self._native_command)
        self.native_input.failed.connect(lambda message: self.statusBar().showMessage(message))
        QApplication.instance().installEventFilter(self.keyboard)
        self.statusBar().showMessage(
            tr("Добавьте презентации, изображения или видео · Ctrl+O — открыть файл")
        )
        if self.settings.warning:
            QTimer.singleShot(0, lambda: self._warning(self.settings.warning))

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("workspace")
        body.setMinimumWidth(850)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 12, 16, 10)
        layout.setSpacing(8)
        header = QHBoxLayout()
        brand_icon = QLabel()
        brand_icon.setPixmap(
            QPixmap(str(Path(__file__).parents[1] / "resources/icons/scene.png")).scaled(
                44,
                44,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        header.addWidget(brand_icon)
        brand_column = QVBoxLayout()
        brand_column.setSpacing(0)
        brand = QLabel(tr("Сцена"))
        brand.setObjectName("heading")
        brand_column.addWidget(brand)
        tagline = QLabel(tr("ПУЛЬТ ВАШЕГО ВЫСТУПЛЕНИЯ"))
        tagline.setObjectName("eyebrow")
        brand_column.addWidget(tagline)
        header.addLayout(brand_column)
        header.addSpacing(20)
        self.document_label = ElidedLabel(tr("Презентации · Изображения · Видео"))
        self.document_label.setObjectName("documentTitle")
        self.document_label.setMinimumWidth(0)
        header.addWidget(self.document_label, 1)
        open_button = QPushButton(tr("Добавить материалы"))
        open_button.setIcon(icon("plus", "#D4C7FF"))
        open_button.setToolTip(tr("Добавить презентации, изображения и видео"))
        open_button.clicked.connect(self.add_presentations)
        header.addWidget(open_button)
        layout.addLayout(header)

        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        toolbar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        controls = QHBoxLayout(toolbar)
        controls.setContentsMargins(12, 9, 12, 9)
        screen_icon = QLabel()
        screen_icon.setPixmap(icon("screen").pixmap(20, 20))
        controls.addWidget(screen_icon)
        controls.addWidget(QLabel(tr("Аудитория")))
        self.monitor_combo = QComboBox()
        self.monitor_combo.setAccessibleName(tr("Монитор аудитории"))
        self.monitor_combo.setMinimumWidth(170)
        self.monitor_combo.setMaximumWidth(320)
        controls.addWidget(self.monitor_combo)
        self.swap_button = QPushButton()
        self.swap_button.setIcon(icon("swap"))
        self.swap_button.setObjectName("iconButton")
        self.swap_button.setAccessibleName(tr("Обмен экранами"))
        self.swap_button.setToolTip(tr("Поменять местами экраны докладчика и аудитории"))
        controls.addWidget(self.swap_button)
        controls.addStretch()
        self.visibility_button = QPushButton(tr("Скрыть экран"))
        self.visibility_button.setIcon(icon("eye"))
        self.visibility_button.setObjectName("quiet")
        self.visibility_button.setEnabled(False)
        controls.addWidget(self.visibility_button)
        self.start_button = QPushButton(tr("Начать · F5"))
        self.start_button.setObjectName("primary")
        self.start_button.setIcon(icon("play", "#FFFFFF"))
        self.start_button.setEnabled(False)
        controls.addWidget(self.start_button)
        self.stop_button = QPushButton(tr("Завершить"))
        self.stop_button.setIcon(icon("stop"))
        self.stop_button.setObjectName("danger")
        self.stop_button.setEnabled(False)
        controls.addWidget(self.stop_button)
        layout.addWidget(toolbar)

        self.backend_status = BackendStatusWidget()
        preferred = self.settings.get("preferred_backend", "auto")
        self.backend_status.preference.setCurrentIndex(
            max(0, self.backend_status.preference.findData(preferred))
        )
        engines = self.backend_manager.availability
        self.backend_status.status.setText(
            tr(
                "PowerPoint: {p0} · LibreOffice: {p1}",
                p0=tr("доступен") if engines.powerpoint else tr("не найден"),
                p1=tr("доступен") if engines.libreoffice else tr("не найден"),
            )
        )

        info = QHBoxLayout()
        self.live_label = QLabel(tr("ПОДГОТОВКА"))
        self.live_label.setObjectName("live")
        info.addWidget(self.live_label)
        self.number_label = QLabel("")
        self.number_label.setObjectName("counter")
        info.addWidget(self.number_label)
        info.addStretch()
        timer_title = QLabel(tr("ТАЙМЕР"))
        timer_title.setObjectName("eyebrow")
        info.addWidget(timer_title)
        self.timer_label = QLabel("00:00:00")
        self.timer_label.setObjectName("timer")
        self.timer_label.setAccessibleName(tr("Время выступления"))
        info.addWidget(self.timer_label)
        self.pause_button = QPushButton(tr("Пауза"))
        self.pause_button.setObjectName("quiet")
        self.pause_button.setToolTip(tr("Приостановить таймер выступления"))
        self.pause_button.setEnabled(False)
        info.addWidget(self.pause_button)
        self.reset_button = QPushButton(tr("Сброс"))
        self.reset_button.setObjectName("quiet")
        self.reset_button.setToolTip(tr("Сбросить таймер выступления"))
        info.addWidget(self.reset_button)
        info.addSpacing(16)
        self.clock_label = QLabel()
        self.clock_label.setObjectName("muted")
        self.clock_label.setAccessibleName(tr("Системное время"))
        info.addWidget(self.clock_label)
        layout.addLayout(info)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(8)
        self.thumbnails = ThumbnailPanel()
        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setMinimumWidth(232)
        self.queue_panel = PresentationQueuePanel(self.queue)
        self.sidebar_tabs.addTab(self.queue_panel, tr("Материалы"))
        self.sidebar_tabs.addTab(self.thumbnails, tr("Слайды"))
        self.main_splitter.addWidget(self.sidebar_tabs)
        current_panel = QWidget()
        current_panel.setObjectName("panel")
        current_layout = QVBoxLayout(current_panel)
        current_layout.setContentsMargins(14, 12, 14, 14)
        current_layout.setSpacing(12)
        preview_header = QHBoxLayout()
        self.current_label = QLabel(tr("ПРЕДПРОСМОТР"))
        self.current_label.setObjectName("eyebrow")
        preview_header.addWidget(self.current_label)
        preview_header.addStretch()
        self.preview_hint = QLabel(tr("Экран аудитории"))
        self.preview_hint.setObjectName("muted")
        preview_header.addWidget(self.preview_hint)
        current_layout.addLayout(preview_header)
        self.current_slide = SlideWidget()
        current_layout.addWidget(self.current_slide, 1)
        self.navigation = NavigationPanel()
        self.navigation.set_content_kind("empty")
        current_layout.addWidget(self.navigation)
        self.main_splitter.addWidget(current_panel)

        self.side_splitter = QSplitter(Qt.Orientation.Vertical)
        self.side_splitter.setChildrenCollapsible(False)
        self.side_splitter.setHandleWidth(8)
        next_panel = QWidget()
        next_panel.setObjectName("panel")
        next_layout = QVBoxLayout(next_panel)
        next_layout.setContentsMargins(14, 12, 14, 14)
        self.next_label = QLabel(tr("ДАЛЕЕ"))
        self.next_label.setObjectName("eyebrow")
        next_layout.addWidget(self.next_label)
        self.next_slide = SlideWidget()
        self.next_slide.prepare(-1, tr("Следующий слайд появится здесь"))
        next_layout.addWidget(self.next_slide, 1)
        self.side_splitter.addWidget(next_panel)
        self.notes_panel = NotesPanel(self.settings.get("notes_font", 16))
        self.side_splitter.addWidget(self.notes_panel)
        self.main_splitter.addWidget(self.side_splitter)
        self.main_splitter.setSizes([270, 750, 340])
        self.main_splitter.setStretchFactor(1, 3)
        self.main_splitter.setStretchFactor(2, 1)
        self.side_splitter.setSizes([260, 430])
        layout.addWidget(self.main_splitter, 1)
        layout.addWidget(self.backend_status)
        self.hint = QLabel(
            tr(
                "Shift+F5 — с выбранного слайда    ·    Номер + Enter — переход    ·    B / W — чёрный / белый экран"
            )
        )
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        scroll.setWidget(body)
        self.setCentralWidget(scroll)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu(tr("Файл"))
        file_menu.addAction(tr("Открыть материал…"), self.open_dialog)
        file_menu.addAction(tr("Добавить материалы…"), self.add_presentations)
        file_menu.addAction(tr("Добавить папку…"), self.add_folder)
        file_menu.addAction(tr("Добавить ссылку Canva…"), self.add_canva)
        self.recent_menu = file_menu.addMenu(tr("Последние документы"))
        self._update_recent_menu()
        file_menu.addAction(tr("Сохранить заметки"), self.save_notes)
        file_menu.addSeparator()
        file_menu.addAction(tr("Выход"), self.close)
        project_menu = self.menuBar().addMenu(tr("Мероприятие"))
        project_menu.addAction(tr("Создать проект"), self.new_project)
        project_menu.addAction(tr("Открыть проект…"), self.open_project)
        project_menu.addAction(tr("Сохранить проект · Ctrl+Shift+S"), self.save_project)
        project_menu.addAction(tr("Сохранить как…"), lambda: self.save_project(True))
        project_menu.addAction(tr("Название мероприятия…"), self.rename_event)
        project_menu.addSeparator()
        self.auto_advance_action = QAction(
            tr("Автоматически переходить к следующей презентации"), self
        )
        self.auto_advance_action.setCheckable(True)
        self.auto_advance_action.toggled.connect(self._auto_advance_changed)
        project_menu.addAction(self.auto_advance_action)
        project_menu.addAction(tr("Проверить все презентации"), self.preflight_all)
        queue_menu = self.menuBar().addMenu(tr("Очередь"))
        queue_menu.addAction(
            tr("Следующая презентация · Ctrl+PageDown"), lambda: self.adjacent_file(1)
        )
        queue_menu.addAction(
            tr("Предыдущая презентация · Ctrl+PageUp"), lambda: self.adjacent_file(-1)
        )
        queue_menu.addAction(
            tr("Открыть выбранную · Ctrl+Enter"),
            lambda: self.load_item(self.queue_panel.selected_id()),
        )
        queue_menu.addAction(
            tr("К списку презентаций · Ctrl+L"), lambda: self.sidebar_tabs.setCurrentIndex(0)
        )
        show_menu = self.menuBar().addMenu(tr("Показ"))
        show_menu.addAction(tr("С первого слайда · F5"), lambda: self.start_presentation(False))
        show_menu.addAction(tr("С выбранного · Shift+F5"), lambda: self.start_presentation(True))
        show_menu.addAction(tr("Завершить · Esc"), self.presentation.stop)
        show_menu.addSeparator()
        show_menu.addAction(tr("Чёрный экран · B"), lambda: self.presentation.toggle_blank("black"))
        show_menu.addAction(tr("Белый экран · W"), lambda: self.presentation.toggle_blank("white"))
        show_menu.addAction(
            tr("Заставка мероприятия"), lambda: self.set_audience_mode(AudienceMode.SPLASH)
        )
        show_menu.addAction(
            tr("Удерживать последний кадр"), lambda: self.set_audience_mode(AudienceMode.HOLD)
        )
        show_menu.addAction(
            tr("Вернуть текущий слайд"), lambda: self.set_audience_mode(AudienceMode.SLIDE)
        )
        language_menu = self.menuBar().addMenu("Язык / Language")
        self.language_actions = QActionGroup(self)
        for code, name in LANGUAGES.items():
            action = language_menu.addAction(name)
            action.setData(code)
            action.setCheckable(True)
            action.setChecked(code == self.settings.get("language", language()))
            self.language_actions.addAction(action)
            action.triggered.connect(lambda checked=False, value=code: self._select_language(value))
        help_menu = self.menuBar().addMenu(tr("Справка"))
        help_menu.addAction(tr("Горячие клавиши"), self._show_help)
        help_menu.addAction(
            tr("WebView2 для Canva…"),
            lambda: QDesktopServices.openUrl(
                QUrl("https://developer.microsoft.com/microsoft-edge/webview2/")
            ),
        )
        self.shortcuts = []
        for sequence, callback in (
            ("Ctrl+O", self.open_dialog),
            ("Ctrl+S", self.save_notes),
            ("Ctrl+N", self._focus_notes),
            ("F5", lambda: self.start_presentation(False)),
            ("Shift+F5", lambda: self.start_presentation(True)),
            ("Ctrl+PageDown", lambda: self.adjacent_file(1)),
            ("Ctrl+PageUp", lambda: self.adjacent_file(-1)),
            ("Ctrl+Return", lambda: self.load_item(self.queue_panel.selected_id())),
            ("Ctrl+L", lambda: self.sidebar_tabs.setCurrentIndex(0)),
            ("Ctrl+Shift+S", self.save_project),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)

    def _connect(self) -> None:
        self.render_debounce = QTimer(self)
        self.render_debounce.setSingleShot(True)
        self.render_debounce.setInterval(45)
        self.render_debounce.timeout.connect(self._render_frame)
        self.autosave = QTimer(self)
        self.autosave.setSingleShot(True)
        self.autosave.setInterval(650)
        self.autosave.timeout.connect(self.save_notes)
        self.clock_tick = QTimer(self)
        self.clock_tick.setInterval(200)
        self.clock_tick.timeout.connect(self._update_clock)
        self.clock_tick.start()
        self._update_clock()
        self.slides.changed.connect(self._slide_changed)
        self.renderer.ready.connect(self._raster_ready)
        self.renderer.failed.connect(self._render_error)
        self.renderer.ended.connect(self._backend_ended)
        self.renderer.video_choices.connect(self._choose_video)
        self.renderer.video_failed.connect(self._video_failed)
        self.renderer.video_state_changed.connect(self._video_state)
        self.renderer.frame_ready.connect(self._video_frame)
        self.preloader.prepared.connect(self._candidate_prepared)
        self.preloader.failed.connect(self._candidate_failed)
        self.handoff.completed.connect(self._handoff_complete)
        self.handoff.failed.connect(self._handoff_failed)
        self.queue.changed.connect(self._queue_changed)
        self.queue_panel.add_requested.connect(self.add_presentations)
        self.queue_panel.folder_requested.connect(self.add_folder)
        self.queue_panel.open_requested.connect(self.load_item)
        self.queue_panel.canva_requested.connect(self.add_canva)
        self.queue_panel.preflight_requested.connect(self.preflight_all)
        self.queue_panel.remove_requested.connect(self._remove_item)
        self.queue_panel.move_requested.connect(self.queue.move)
        self.backend_status.preference_changed.connect(self._preference_changed)
        self.backend_status.warnings_requested.connect(self.show_media_warnings)
        self.thumbnails.selected.connect(self.slides.go_to)
        self.thumbnails.visible_changed.connect(self.schedule_render)
        self.navigation.previous.clicked.connect(self.slides.previous)
        self.navigation.next.clicked.connect(self.slides.next)
        self.navigation.go_requested.connect(self.slides.go_to_number)
        self.navigation.media.command_requested.connect(self._video_command)
        self.navigation.scale.changed.connect(self._scale_changed)
        self.current_slide.panned.connect(self._media_panned)
        self.notes_panel.edited.connect(self._note_edited)
        self.notes_panel.save_requested.connect(self.save_notes)
        self.start_button.clicked.connect(lambda: self.start_presentation(False))
        self.stop_button.clicked.connect(self.presentation.stop)
        self.visibility_button.clicked.connect(self.toggle_audience)
        self.pause_button.clicked.connect(self._pause_timer)
        self.reset_button.clicked.connect(self.timer.reset)
        self.swap_button.clicked.connect(self.swap_monitors)
        self.monitor_combo.currentIndexChanged.connect(self._monitor_selected)
        self.monitors.changed.connect(self._refresh_monitors)
        self.presentation.started.connect(self._show_started)
        self.presentation.stopped.connect(self._show_stopped)
        self.presentation.blank_changed.connect(self._blank_changed)
        self.presentation.number_changed.connect(
            lambda value: self.number_label.setText(
                tr("Перейти: {p0} ↵", p0=value) if value else ""
            )
        )
        self.presentation.invalid_number.connect(
            lambda: self.statusBar().showMessage(
                tr("Введите номер от 1 до {p0}", p0=self.slides.count), 5000
            )
        )
        self.audience.closed.connect(self.presentation.stop)
        for widget in (self.current_slide, self.next_slide, self.audience.slide):
            widget.resized.connect(self.schedule_render)

    def _update_recent_menu(self) -> None:
        self.recent_menu.clear()
        recent = self.settings.get("recent_files", [])
        self.recent_menu.setEnabled(bool(recent))
        for path in recent:
            action = QAction(path, self)
            action.triggered.connect(lambda checked=False, filename=path: self.load_pdf(filename))
            self.recent_menu.addAction(action)

    def open_dialog(self) -> None:
        if QApplication.activeModalWidget() is not None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Открыть материал"),
            "",
            file_filter(),
        )
        if path:
            self.load_pdf(path)

    def _focus_notes(self) -> None:
        if self.notes_panel.isEnabled():
            self.activateWindow()
            self.notes_panel.editor.setFocus()

    def load_pdf(self, path: str, password: str = "") -> None:
        """Compatibility entry point, now accepts all supported presentation formats."""
        normalized = normalize_canva_url(path) if is_canva_url(path) else str(Path(path).resolve())
        item = self.queue.get(self._pending_item) if password else None
        if item is None:
            item = next(
                (
                    entry
                    for entry in self.queue.items
                    if entry.path.casefold() == normalized.casefold()
                ),
                None,
            )
        if item is None:
            added = self.queue.add([normalized], self.backend_status.preference.currentData())
            if not added:
                self._warning(
                    tr(
                        "Поддерживаются PDF, PowerPoint, изображения и видео. Выберите подходящий тип файла."
                    )
                )
                return
            item = added[0]
        self.load_item(item.id, password)

    def add_canva(self):
        value, accepted = QInputDialog.getText(
            self, tr("Презентация Canva"), tr("Ссылка на просмотр Canva (нужен интернет):")
        )
        if not accepted or not value.strip():
            return
        try:
            path = normalize_canva_url(value)
        except ValueError as exc:
            self._warning(str(exc))
            return
        self.load_pdf(path)

    def load_item(self, item_id: str, password: str = "") -> None:
        item = self.queue.get(item_id)
        if item is None:
            return
        if self.handoff.busy:
            self.statusBar().showMessage(
                tr("Передача экрана выполняется. Для отмены завершите показ.")
            )
            return
        if not self.save_notes():
            return
        if item.id == self.queue.active_id and self.document is not None and not password:
            try:
                same_engine = (
                    self.backend_manager.choose(item.path, item.preferred_backend).kind
                    == self.renderer.kind
                )
            except RuntimeError:
                same_engine = False
            if same_engine:
                self.sidebar_tabs.setCurrentIndex(
                    0 if self.renderer.kind in {"image", "video"} else 1
                )
                return
        self._preflight_ids.clear()
        self._preflight_running = False
        self._pending_item = item.id
        self._loading_path = item.path
        self.loading = True
        self.notes_panel.setEnabled(False)
        self.navigation.setEnabled(False)
        self.thumbnails.setEnabled(False)
        self.start_button.setEnabled(False)
        self.statusBar().showMessage(
            tr("Подготовка {p0}… Текущий показ сохраняется.", p0=item.name)
        )
        self.preloader.prepare(item, password)

    def _candidate_prepared(self, item_id: str, backend, preview) -> None:
        if item_id == self._pending_item:
            result = self.preloader.take(item_id)
            if result is None:
                return
            self._switch_candidate = (item_id, backend, preview)
            if self.presentation.active:
                target = self._audience_target()
                if target is None:
                    self._handoff_failed(tr("Экран аудитории недоступен."))
                    return
                self.handoff.switch(
                    self.renderer, backend, self.queue.get(item_id).last_slide, target
                )
            else:
                self._commit_candidate()
        elif self._preflight_running:
            self.preloader.cancel()
            QTimer.singleShot(0, self._preflight_next)

    def _candidate_failed(self, item_id: str, kind: str, message: str) -> None:
        log.warning("Presentation %s: %s", item_id, message)
        if item_id == self._pending_item:
            self._load_failed(kind, message)
        elif self._preflight_running:
            self.preloader.cancel()
            QTimer.singleShot(0, self._preflight_next)

    def _handoff_complete(self, backend) -> None:
        if self._switch_candidate is not None:
            self._commit_candidate()
        if not self.audience.preview:
            self.activateWindow()
            self.setFocus()
        self._update_live_label()
        self.native_input.set_target(getattr(backend, "native_hwnd", 0))

    def _handoff_failed(self, message: str) -> None:
        if self._switch_candidate:
            item_id, backend, _ = self._switch_candidate
            self.queue.update(item_id, state=QueueState.ERROR, error=message)
            backend.dispose()
            backend.deleteLater()
            self._switch_candidate = None
        self.loading = False
        self._pending_item = ""
        self.presentation.active = False
        self.timer.pause()
        self.audience_display.handoff = False
        self.audience_display.apply_mode(AudienceMode.BLACK)
        self.start_button.setEnabled(self.document is not None)
        self.navigation.setEnabled(self.document is not None)
        self.notes_panel.setEnabled(self.notes is not None)
        self.thumbnails.setEnabled(True)
        self._warning(message)

    def _commit_candidate(self) -> None:
        if self._switch_candidate is None:
            return
        item_id, backend, preview = self._switch_candidate
        self._switch_candidate = None
        previous = self.renderer
        self.slides.bind_backend(None)
        previous.ready.disconnect(self._raster_ready)
        previous.failed.disconnect(self._render_error)
        previous.ended.disconnect(self._backend_ended)
        previous.video_choices.disconnect(self._choose_video)
        previous.video_failed.disconnect(self._video_failed)
        previous.video_state_changed.disconnect(self._video_state)
        previous.frame_ready.disconnect(self._video_frame)
        self.navigation.media.reset()
        self.renderer = backend
        backend.ready.connect(self._raster_ready)
        backend.failed.connect(self._render_error)
        backend.ended.connect(self._backend_ended)
        backend.video_choices.connect(self._choose_video)
        backend.video_failed.connect(self._video_failed)
        backend.video_state_changed.connect(self._video_state)
        backend.frame_ready.connect(self._video_frame)
        backend.native_window_changed.connect(self._native_window_changed)
        self.queue.activate(item_id)
        self._pending_item = ""
        last_slide = self.queue.get(item_id).last_slide
        self._loaded(backend.document)
        self.slides.bind_backend(backend)
        item = self.queue.get(item_id)
        if backend.active:
            self.slides.sync_current(backend.current)
        else:
            self.slides.go_to(last_slide)
        if preview and preview[0] == self.slides.current:
            self.current_slide.set_raster(*preview)
            self.audience.slide.page = preview[0]
            self.audience.slide.set_raster(*preview)
        if previous is not backend:
            previous.dispose()
            previous.deleteLater()
        self.queue_panel.select(item_id)
        self.sidebar_tabs.setCurrentIndex(0 if backend.kind in {"image", "video"} else 1)
        self.backend_status.set_backend(backend, item.warnings)
        self.audience_display.backend = backend
        self._update_live_label()
        QTimer.singleShot(0, self._prepare_next)

    def _can_play_video(self) -> bool:
        return (
            self.presentation.active
            and self.renderer.active
            and self.renderer.get_capabilities().video_controls
            and not self.loading
            and not self.handoff.busy
            and not self._closing
            and self.audience.isVisible()
            and self.audience_display.mode == AudienceMode.SLIDE
        )

    def play_video(self) -> None:
        if self._can_play_video():
            self.renderer.play_video(slide_index=self.slides.current)

    def _video_state(self, index: int, videos: list[dict]) -> None:
        if self.sender() is self.renderer and index == self.slides.current:
            self.navigation.media.update_state(index, videos)

    def _video_frame(self, image) -> None:
        if self.sender() is self.renderer and self.renderer.active:
            self.current_slide.image = image
            self.current_slide.update()

    def _video_command(self, index: int, identifier: int, action: str, value: int) -> None:
        if self._can_play_video() and index == self.slides.current:
            accepted = self.renderer.control_video(
                action, identifier, slide_index=index, value=value
            )
            if accepted and action == "volume" and self.queue.active:
                self._set_media_settings(volume=max(0, min(100, value)))
            elif accepted and action == "loop" and self.queue.active:
                if self.renderer.kind == "video":
                    self._set_media_settings(loop=bool(value))

    def _set_media_settings(self, **values):
        if not self.queue.active or self.loading or self.handoff.busy:
            return
        settings = {**self.queue.active.media_settings, **values}
        self.queue.update(self.queue.active_id, media_settings=settings)
        self.renderer.set_media_settings(settings)
        self._sync_media_view()
        self.schedule_render()

    def _scale_changed(self, mode, zoom):
        self._set_media_settings(scale=mode, zoom=zoom, pan_x=0, pan_y=0)

    def _media_panned(self, x, y):
        self._set_media_settings(pan_x=x, pan_y=y)

    def _sync_media_view(self):
        self.navigation.set_content_kind(self.renderer.kind if self.document else "empty")
        self.hint.setText(
            tr(
                "Ctrl+PgDn — следующий материал    ·    B / W — чёрный / белый экран    ·    Esc — завершить показ"
            )
            if self.document and self.renderer.kind in {"image", "video"}
            else tr(
                "Shift+F5 — с выбранного слайда    ·    Номер + Enter — переход    ·    B / W — чёрный / белый экран"
            )
        )
        scalable = self.document is not None and self.renderer.get_capabilities().scaling
        self.navigation.media.setVisible(
            self.document is not None and self.renderer.get_capabilities().video_controls
        )
        self.navigation.scale.setVisible(scalable)
        if not scalable:
            self.current_slide.set_media_view()
            if self.audience_display.mode == AudienceMode.SLIDE and not self.handoff.busy:
                self.audience.slide.set_media_view()
            return
        settings = self.renderer.media_settings
        source = self.document.page_sizes[0]
        self.navigation.scale.set_settings(settings)
        if self.presentation.active and self.audience.isVisible():
            reference = self.audience.slide.render_size()
        else:
            screen = self.monitors.resolve(self.monitor_combo.currentData()) or self.screen()
            reference = (
                round(screen.size().width() * screen.devicePixelRatio()),
                round(screen.size().height() * screen.devicePixelRatio()),
            )
        self.current_slide.set_media_view(source, settings, reference)
        if self.audience_display.mode == AudienceMode.SLIDE and not self.handoff.busy:
            self.audience.slide.set_media_view(source, settings)

    def _choose_video(self, index: int, videos: list[dict]) -> None:
        backend = self.sender()
        if backend is not self.renderer or not self._can_play_video():
            return
        labels = [f"{number}. {video['name']}" for number, video in enumerate(videos, 1)]
        selected, accepted = QInputDialog.getItem(
            self, tr("Запустить видео"), tr("Видео на текущем слайде:"), labels, 0, False
        )
        if accepted and backend is self.renderer and self._can_play_video():
            if self.slides.current != index:
                self._video_failed(tr("Слайд изменился. Выберите видео на текущем слайде."))
                return
            backend.play_video(videos[labels.index(selected)]["id"], slide_index=index)

    def _video_failed(self, message: str) -> None:
        # Feedback stays in the presenter, without blanking or stopping the show.
        self.statusBar().showMessage(message, 10000)

    def _native_window_changed(self, hwnd: int) -> None:
        self.audience_display.native_hwnd = hwnd
        self.native_input.set_target(hwnd)

    def _native_command(self, command: str) -> None:
        if not self.presentation.active or QApplication.activeModalWidget() is not None:
            return
        if command == "escape":
            self.presentation.escape()
            return
        if self.loading or self.handoff.busy:
            return
        if command.startswith("digit:"):
            self.presentation.digit(command[-1])
            return
        actions = {
            "start": self.start_presentation,
            "start_current": lambda: self.start_presentation(True),
            "next": self.slides.next,
            "previous": self.slides.previous,
            "first": lambda: self.slides.go_to(0),
            "last": lambda: self.slides.go_to(self.slides.count - 1),
            "black": lambda: self.presentation.toggle_blank("black"),
            "white": lambda: self.presentation.toggle_blank("white"),
            "backspace": self.presentation.backspace,
            "submit": self.presentation.submit_number,
            "open": self.open_dialog,
            "save_notes": self.save_notes,
            "save_project": self.save_project,
            "notes": self.notes_panel.editor.setFocus,
            "previous_file": lambda: self.adjacent_file(-1),
            "next_file": lambda: self.adjacent_file(1),
            "open_selected": lambda: self.load_item(self.queue_panel.selected_id()),
            "queue": lambda: self.sidebar_tabs.setCurrentIndex(0),
        }
        action = actions.get(command)
        if action:
            if command in {"open", "save_project", "notes", "queue"}:
                self.activateWindow()
            action()

    def _prepare_next(self) -> None:
        if self.queue.active is None:
            return
        if self.loading or self._preflight_running or self.handoff.busy or self._closing:
            return
        item = self.queue.adjacent(1)
        if item and (self.queue.active is None or item.path != self.queue.active.path):
            self.preloader.prepare(item)

    def _backend_ended(self) -> None:
        if self.handoff.busy:
            return
        if self.renderer.kind == "video" and not self.project.auto_advance:
            return  # Keep the last frame and player available for replay.
        if self.project.auto_advance and self.queue.adjacent(1):
            self.adjacent_file(1)
        else:
            self.presentation.stop()

    def _loaded(self, document: PresentationDocument) -> None:
        self.loading = False
        self.document = document
        self._notes_error_shown = False
        self.notes = None
        try:
            self.notes = NotesManager(document.fingerprint, self.data_root)
            if document.native_notes and not self.notes.path.exists():
                for index, text in enumerate(document.native_notes):
                    self.notes.set(index, text)
                self.autosave.start()
            if self.notes.warning:
                self._warning(self.notes.warning)
        except StorageError as exc:
            self._warning(tr("{p0}\nРедактор заметок отключён для защиты исходных данных.", p0=exc))
        self.notes_panel.setEnabled(self.notes is not None)
        self.navigation.setEnabled(True)
        self.thumbnails.setEnabled(True)
        self.start_button.setEnabled(True)
        self.current_slide.prepare(-1)
        self.next_slide.prepare(-1)
        if not self.presentation.active:
            self.audience.slide.prepare(-1)
        self.thumbnails.set_document(document.page_count)
        self.slides.set_document(document.page_count)
        self._sync_media_view()
        detail = (
            self.renderer.label
            if self.renderer.kind in {"image", "video"}
            else tr("{p0} слайдов", p0=document.page_count)
        )
        name = document.title if self.renderer.kind == "canva" else Path(document.path).name
        self.document_label.setText(f"{name}  ·  {detail}")
        self.document_label.setToolTip(f"{document.title}\n{document.path}")
        self.setWindowTitle(tr("{p0} — Сцена", p0=name))
        self.settings.add_recent(document.path)
        self._update_recent_menu()
        self._save_settings()
        warnings = self.queue.active.warnings if self.queue.active else []
        self.statusBar().showMessage(
            warnings[0]
            if warnings
            else tr("Презентация готова · F5 — с начала · Shift+F5 — с выбранного слайда")
        )

    def _load_failed(self, kind: str, message: str) -> None:
        self.loading = False
        self.notes_panel.setEnabled(self.notes is not None)
        self.navigation.setEnabled(self.document is not None)
        self.thumbnails.setEnabled(True)
        self.start_button.setEnabled(self.document is not None)
        if kind == "password":
            password, accepted = QInputDialog.getText(
                self, tr("Защищённый PDF"), message, QLineEdit.EchoMode.Password
            )
            if accepted:
                self.load_pdf(self._loading_path, password)
                return
            self.statusBar().showMessage(tr("Открытие отменено"))
        else:
            self._warning(message)
            self.statusBar().showMessage(tr("Не удалось открыть документ"))
        self._pending_item = ""

    def _slide_changed(self, page: int) -> None:
        if self.document is None:
            return
        self.navigation.media.reset(page)
        self.renderer.begin_frame()
        self.current_slide.prepare(page)
        self.audience.slide.page = page
        next_page = page + 1 if page + 1 < self.slides.count else -1
        media = self.renderer.kind in {"image", "video"}
        self.next_slide.prepare(
            next_page,
            tr("Выберите следующий материал в очереди слева")
            if media
            else tr("Последний слайд презентации")
            if next_page < 0
            else tr("Загрузка слайда…"),
        )
        kind = {"image": tr("ИЗОБРАЖЕНИЕ"), "video": tr("ВИДЕО")}.get(self.renderer.kind)
        self.current_label.setText(
            kind or tr("СЛАЙД {p0:02} / {p1:02}", p0=page + 1, p1=self.slides.count)
        )
        self.next_label.setText(
            tr("ДАЛЕЕ В ВЫСТУПЛЕНИИ")
            if media
            else tr("ДАЛЕЕ · {p0:02}", p0=page + 2)
            if next_page >= 0
            else tr("КОНЕЦ ПРЕЗЕНТАЦИИ")
        )
        self.navigation.update_state(page, self.slides.count)
        self.thumbnails.set_current(page)
        self.notes_panel.set_note(page, self.notes.get(page) if self.notes else "")
        if self.queue.active:
            self.queue.update(self.queue.active_id, last_slide=page)
            self._project_dirty = True
        self.schedule_render()

    def schedule_render(self) -> None:
        if not self._closing:
            self.render_debounce.start()

    def _render_frame(self) -> None:
        if self.document is None:
            return
        self._sync_media_view()
        self.renderer.begin_frame()
        page = self.slides.current
        if self.presentation.active and self.audience.isVisible():
            self.renderer.request("audience", page, *self.audience.slide.render_size(), priority=0)
        self.renderer.request("current", page, *self.current_slide.render_size(), priority=1)
        self.renderer.request("next", page + 1, *self.next_slide.render_size(), priority=2)
        # Adjacent slides at presenter and audience resolution are ready for the next click.
        for adjacent in (page + 1, page - 1):
            self.renderer.request(
                "prefetch", adjacent, *self.current_slide.render_size(), priority=4
            )
            if self.presentation.active and self.audience.isVisible():
                self.renderer.request(
                    "prefetch", adjacent, *self.audience.slide.render_size(), priority=4
                )
        for visible in self.thumbnails.visible_pages():
            self.renderer.request("thumbnail", visible, 300, 188, priority=3)

    def _raster_ready(self, tag: str, page: int, raster: Raster) -> None:
        if tag == "thumbnail":
            self.thumbnails.set_raster(page, raster)
        elif tag == "audience":
            self.audience_display.set_raster(page, raster)
        else:
            widget = {
                "current": self.current_slide,
                "next": self.next_slide,
                "audience": self.audience.slide,
            }.get(tag)
            if widget:
                widget.set_raster(page, raster)

    def _render_error(self, message: str) -> None:
        log.error(message)
        self.statusBar().showMessage(message)
        if (
            self.renderer.get_capabilities().native_window
            and not self.renderer.active
            and self.presentation.active
        ):
            self.audience_display.handoff = False
            self.audience_display.apply_mode(AudienceMode.BLACK)
            self.presentation.active = False
            self.timer.pause()
            self.native_input.set_target(0)
            self._update_live_label()
            if self.queue.active:
                self.queue.update(self.queue.active_id, state=QueueState.ERROR, error=message)
        for widget in (self.current_slide, self.next_slide):
            if widget.image.isNull():
                widget.message = tr(
                    "Не удалось отобразить слайд. Попробуйте открыть презентацию повторно."
                )
                widget.update()

    def _note_edited(self, text: str) -> None:
        if self.notes and not self.loading:
            self.notes.set(self.slides.current, text)
            self.notes_panel.status.setText(tr("Сохранение…"))
            self.autosave.start()

    def save_notes(self) -> bool:
        self.autosave.stop()
        try:
            if self.notes:
                self.notes.save()
            self.notes_panel.status.setText(tr("Сохранено"))
            self._notes_error_shown = False
            return True
        except StorageError as exc:
            self.notes_panel.status.setText(tr("Ошибка сохранения"))
            if not self._notes_error_shown:
                self._notes_error_shown = True
                self._warning(str(exc))
            return False

    def start_presentation(self, from_current: bool = False) -> None:
        if not self.loading and not self.handoff.busy and QApplication.activeModalWidget() is None:
            self.presentation.start(from_current)

    def _show_started(self) -> None:
        self.stop_button.setEnabled(True)
        self.visibility_button.setEnabled(True)
        self.pause_button.setEnabled(True)
        target = self._audience_target()
        if target is None:
            self.presentation.stop()
            return
        self.audience_display.mode = AudienceMode.SLIDE
        if self.handoff.busy:
            return
        self.handoff.switch(
            self.renderer if self.renderer.active else None,
            self.renderer,
            self.presentation.requested_start_index,
            target,
        )
        self._update_clock()
        self._update_live_label()

    def _show_stopped(self) -> None:
        self.native_input.set_target(0)
        self.handoff.cancel()
        self.renderer.stop()
        if self._switch_candidate is not None:
            item_id, backend, _ = self._switch_candidate
            self._switch_candidate = None
            backend.dispose()
            backend.deleteLater()
            self.queue.update(item_id, state=QueueState.WAITING)
            self._pending_item = ""
            self.loading = False
            self.notes_panel.setEnabled(self.notes is not None)
            self.navigation.setEnabled(self.document is not None)
            self.thumbnails.setEnabled(True)
            self.start_button.setEnabled(self.document is not None)
        self.audience_display.stop()
        self.stop_button.setEnabled(False)
        self.visibility_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self._update_live_label()
        self._update_clock()

    def _blank_changed(self, color: str) -> None:
        self.audience_display.apply_mode(color or AudienceMode.SLIDE)
        self._update_live_label()

    def set_audience_mode(self, mode: AudienceMode) -> None:
        if not self.presentation.active:
            return
        self.presentation.blank = ""
        self.audience_display.splash_text = self.project.show_settings.get(
            "splash_text", self.project.name
        )
        self.audience_display.apply_mode(mode)
        if mode == AudienceMode.SLIDE:
            self.schedule_render()
        self._update_live_label()

    def _update_live_label(self) -> None:
        if not self.presentation.active:
            text = tr("ПОДГОТОВКА")
        elif not self.audience.isVisible():
            text = tr("ЭКРАН СКРЫТ")
        elif self.presentation.blank:
            text = tr("ЧЁРНЫЙ ЭКРАН") if self.presentation.blank == "black" else tr("БЕЛЫЙ ЭКРАН")
        elif self.audience_display.mode == AudienceMode.HOLD:
            text = tr("КАДР УДЕРЖИВАЕТСЯ")
        elif self.audience_display.mode == AudienceMode.SPLASH:
            text = tr("ЗАСТАВКА")
        elif self.handoff.busy:
            text = tr("ПЕРЕДАЧА ЭКРАНА")
        else:
            text = tr("ПРЕДПРОСМОТР") if self.audience.preview else tr("● В ЭФИРЕ")
        self.live_label.setText(text)
        state = (
            "live"
            if text in {tr("● В ЭФИРЕ"), tr("ПРЕДПРОСМОТР")}
            else "covered"
            if self.presentation.active
            else "idle"
        )
        if self.live_label.property("state") != state:
            self.live_label.setProperty("state", state)
            self.live_label.style().unpolish(self.live_label)
            self.live_label.style().polish(self.live_label)
        self.navigation.media.set_available(self._can_play_video())

    def _place_audience(self) -> None:
        target = self._audience_target()
        if target and self.renderer.active:
            self.renderer.set_display_target(target)
            self.audience_display.attach(self.renderer)

    def _audience_target(self):
        screen = self.monitors.resolve(self.monitor_combo.currentData())
        if screen is None:
            screen = self.monitors.default_audience(self.screen())
        if screen:
            target = self.audience_display.place(screen)
            self.visibility_button.setText(tr("Скрыть экран"))
            self.schedule_render()
            self._update_live_label()
            if not target.preview:
                self.activateWindow()
                self.setFocus()
            return target
        return None

    def toggle_audience(self) -> None:
        if not self.presentation.active:
            return
        if self.audience.isVisible():
            if self.renderer.get_capabilities().native_window:
                self.renderer.set_blank("pause")
                self._native_visibility(False)
            self.audience_display.stop()
            self.visibility_button.setText(tr("Показать экран"))
        else:
            self._place_audience()
            self._native_visibility(True)
        self._update_live_label()

    def _refresh_monitors(self) -> None:
        old = self.monitor_combo.currentData() or self.settings.get("audience_monitor", "")
        screens = self.monitors.screens()
        if (
            self.presentation.active
            and self.renderer.get_capabilities().native_window
            and self.renderer.target
            and self.monitors.resolve(self.renderer.target.name) is None
        ):
            self.presentation.stop()
            self.statusBar().showMessage(tr("Экран аудитории отключён. Нативный показ остановлен."))
        self.monitor_combo.blockSignals(True)
        self.monitor_combo.clear()
        for index, screen in enumerate(screens):
            size = screen.geometry().size()
            self.monitor_combo.addItem(
                f"{index + 1}. {screen.name()} · {size.width()}×{size.height()}", screen.name()
            )
        selected = self.monitors.resolve(old)
        if selected is None:
            selected = self.monitors.default_audience(self.screen())
        if selected:
            self.monitor_combo.setCurrentIndex(self.monitor_combo.findData(selected.name()))
        self.monitor_combo.blockSignals(False)
        self.swap_button.setEnabled(len(screens) > 1)
        if self.presentation.active and self.audience.isVisible():
            self._place_audience()

    def _monitor_selected(self, index: int) -> None:
        if index < 0:
            return
        self.settings.set("audience_monitor", self.monitor_combo.currentData())
        if self.presentation.active and self.audience.isVisible():
            self._place_audience()

    def swap_monitors(self) -> None:
        presenter = self.screen()
        target = self.monitors.resolve(self.monitor_combo.currentData())
        if presenter and target and presenter != target:
            self.audience.hide()
            self.monitors.move_presenter(self, target)
            self.monitor_combo.setCurrentIndex(self.monitor_combo.findData(presenter.name()))
            if self.presentation.active:
                self._place_audience()

    def _native_visibility(self, visible: bool) -> None:
        hwnd = getattr(self.renderer, "native_hwnd", 0)
        if hwnd:
            try:
                import win32con
                import win32gui

                if win32gui.IsWindow(hwnd):
                    win32gui.ShowWindow(
                        hwnd, win32con.SW_SHOWNOACTIVATE if visible else win32con.SW_HIDE
                    )
            except (ImportError, OSError):
                pass

    def _pause_timer(self) -> None:
        if self.timer.running:
            self.timer.pause()
        else:
            self.timer.resume()
        self._update_clock()

    def _update_clock(self) -> None:
        self.timer_label.setText(self.timer.formatted())
        self.clock_label.setText(datetime.now().strftime("%H:%M:%S"))
        self.pause_button.setText(tr("Пауза") if self.timer.running else tr("Продолжить"))
        self.navigation.media.set_available(self._can_play_video())

    def _restore_settings(self) -> None:
        for key, target, method in (
            ("geometry", self, "restoreGeometry"),
            ("main_splitter", self.main_splitter, "restoreState"),
            ("side_splitter", self.side_splitter, "restoreState"),
        ):
            value = self.settings.get(key, "")
            if value:
                getattr(target, method)(
                    QByteArray.fromBase64(value.encode("ascii", errors="ignore"))
                )

    def _save_settings(self) -> bool:
        self.settings.set("notes_font", self.notes_panel.font_size.value())
        self.settings.set("audience_monitor", self.monitor_combo.currentData() or "")
        for key, state in (
            ("geometry", self.saveGeometry()),
            ("main_splitter", self.main_splitter.saveState()),
            ("side_splitter", self.side_splitter.saveState()),
        ):
            self.settings.set(key, bytes(state.toBase64()).decode("ascii"))
        try:
            self.settings.save()
            return True
        except StorageError as exc:
            self.statusBar().showMessage(str(exc))
            return False

    def _warning(self, message: str) -> None:
        QMessageBox.warning(self, tr("Сцена"), message)

    def _select_language(self, code: str) -> None:
        previous = self.settings.get("language", language())
        self.settings.set("language", code)
        try:
            self.settings.save()
        except StorageError as exc:
            self.settings.set("language", previous)
            for action in self.language_actions.actions():
                action.setChecked(action.data() == previous)
            self._warning(str(exc))
            return
        if code != language():
            QMessageBox.information(
                self,
                "Язык / Language",
                tr("Язык изменится после перезапуска приложения. Текущий показ продолжается."),
            )

    def add_presentations(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Добавить материалы"), "", file_filter())
        if paths:
            added = self.queue.add(paths, self.backend_status.preference.currentData())
            self.sidebar_tabs.setCurrentIndex(0)
            if added:
                self.queue_panel.select(added[0].id)
                if self.document is None:
                    self.load_item(added[0].id)

    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("Папка с материалами"))
        if folder:
            try:
                added = self.queue.add_folder(folder, self.backend_status.preference.currentData())
                self.sidebar_tabs.setCurrentIndex(0)
                if added:
                    self.queue_panel.select(added[0].id)
                else:
                    self.statusBar().showMessage(tr("В этой папке нет поддерживаемых материалов."))
            except OSError as exc:
                self._warning(tr("Не удалось прочитать папку: {p0}", p0=exc))

    def _remove_item(self, item_id: str) -> None:
        if item_id == self._pending_item or self.handoff.busy:
            self.statusBar().showMessage(tr("Дождитесь подготовки перед удалением презентации."))
            return
        if self.preloader.item_id == item_id:
            self.preloader.cancel()
        self.queue.remove(item_id)

    def adjacent_file(self, direction: int) -> None:
        item = self.queue.adjacent(direction)
        if item:
            self.load_item(item.id)
        else:
            self.statusBar().showMessage(
                tr("Это последняя презентация.") if direction > 0 else tr("Это первая презентация.")
            )

    def _queue_changed(self) -> None:
        self.project.items = self.queue.items
        self._project_dirty = True

    def _preference_changed(self, preference: str) -> None:
        self.settings.set("preferred_backend", preference)
        item = self.queue.get(self.queue_panel.selected_id())
        if item:
            self.queue.update(item.id, preferred_backend=preference)
            self._project_dirty = True
            if item.id == self.preloader.item_id:
                self.preloader.cancel()
            self.statusBar().showMessage(
                tr("Выбранный движок будет применён при следующем открытии презентации.")
            )

    def _auto_advance_changed(self, enabled: bool) -> None:
        self.project.auto_advance = enabled
        self._project_dirty = True

    def show_media_warnings(self) -> None:
        item = self.queue.active
        if item:
            MediaWarningDialog(item.name, item.warnings, self).exec()

    def preflight_all(self) -> None:
        if self.loading or self.handoff.busy:
            self.statusBar().showMessage(
                tr("Дождитесь текущего переключения перед проверкой очереди.")
            )
            return
        self.preloader.cancel()
        self._preflight_ids = [
            item.id for item in self.queue.items if item.id != self.queue.active_id
        ]
        self._preflight_running = True
        if self.queue.active:
            active = self.queue.active
            if is_canva_url(active.path) or Path(active.path).is_file():
                self.queue.update(active.id, slide_count=self.document.page_count)
            else:
                self.queue.update(
                    active.id,
                    warnings=[
                        *active.warnings,
                        tr(
                            "Исходный файл больше не найден. Текущий показ загружен, повторное открытие невозможно."
                        ),
                    ],
                )
        self._preflight_dialog = PreflightDialog(self.queue, len(self.monitors.screens()), self)
        self._preflight_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._preflight_dialog.show()
        self._preflight_next()

    def _preflight_next(self) -> None:
        if not self._preflight_running:
            return
        while self._preflight_ids:
            item = self.queue.get(self._preflight_ids.pop(0))
            if item is not None:
                self.preloader.prepare(item)
                return
        self._preflight_running = False
        self.statusBar().showMessage(
            tr("Проверка очереди завершена. Ошибки и ограничения показаны в списке готовности.")
        )
        self._prepare_next()

    def rename_event(self) -> None:
        name, accepted = QInputDialog.getText(
            self, tr("Мероприятие"), tr("Название и текст заставки:"), text=self.project.name
        )
        if accepted and name.strip():
            self.project.name = name.strip()
            self.project.show_settings["splash_text"] = name.strip()
            self.audience_display.splash_text = name.strip()
            self._project_dirty = True

    def _confirm_project_replace(self) -> bool:
        if not self.project.path or not self._project_dirty:
            return True
        answer = QMessageBox.question(
            self,
            tr("Сохранить проект?"),
            tr("В проекте есть несохранённые изменения."),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        return self.save_project() if answer == QMessageBox.StandardButton.Save else True

    def _clear_event(self) -> None:
        self.presentation.stop()
        self.preloader.cancel()
        self._preflight_running = False
        self._preflight_ids.clear()
        self._pending_item = ""
        self.loading = False
        self.slides.bind_backend(None)
        previous = self.renderer
        previous.ready.disconnect(self._raster_ready)
        previous.failed.disconnect(self._render_error)
        previous.ended.disconnect(self._backend_ended)
        previous.dispose()
        previous.deleteLater()
        self.renderer = PDFBackend(self)
        self.renderer.ready.connect(self._raster_ready)
        self.renderer.failed.connect(self._render_error)
        self.renderer.ended.connect(self._backend_ended)
        self.renderer.video_choices.connect(self._choose_video)
        self.renderer.video_failed.connect(self._video_failed)
        self.renderer.video_state_changed.connect(self._video_state)
        self.renderer.frame_ready.connect(self._video_frame)
        self.document = self.notes = None
        self.navigation.media.reset()
        self._sync_media_view()
        self.audience_display.backend = None
        self.slides.set_document(0)
        self.thumbnails.set_document(0)
        self.current_slide.prepare(-1)
        self.next_slide.prepare(-1)
        self.notes_panel.set_note(0, "")
        self.notes_panel.setEnabled(False)
        self.navigation.setEnabled(False)
        self.start_button.setEnabled(False)
        self.document_label.setText(tr("Добавьте презентации мероприятия"))
        self.setWindowTitle(tr("Сцена"))
        self.queue.replace([])
        self.sidebar_tabs.setCurrentIndex(0)

    def new_project(self) -> None:
        if not self.save_notes() or not self._confirm_project_replace():
            return
        self._clear_event()
        self.project = EventProject(items=self.queue.items)
        self.auto_advance_action.setChecked(False)
        self._project_dirty = False

    def open_project(self, path: str = "") -> None:
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, tr("Открыть мероприятие"), "", tr("Сцена (*.pdfpresenter)")
            )
        if not path or not self.save_notes() or not self._confirm_project_replace():
            return
        try:
            project, warning = self.project_manager.load(Path(path))
        except StorageError as exc:
            self._warning(str(exc))
            return
        self._clear_event()
        self.project = project
        self.queue.replace(project.items)
        self.auto_advance_action.setChecked(project.auto_advance)
        self.audience_display.splash_text = project.show_settings.get("splash_text", project.name)
        monitor = project.monitor_settings.get("audience_monitor", "")
        index = self.monitor_combo.findData(monitor)
        if index >= 0:
            self.monitor_combo.setCurrentIndex(index)
        self._project_dirty = False
        self.document_label.setText(project.name)
        self.statusBar().showMessage(
            tr("Проект открыт. Выберите презентацию или проверьте готовность всех файлов.")
        )
        if warning:
            self._warning(warning)

    def save_project(self, save_as: bool = False) -> bool:
        path = self.project.path
        if save_as or path is None:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                tr("Сохранить мероприятие"),
                str(path or tr("Мероприятие.pdfpresenter")),
                tr("Сцена (*.pdfpresenter)"),
            )
            if not filename:
                return False
            path = Path(filename)
        self.project.items = self.queue.items
        self.project.monitor_settings = {
            "audience_monitor": self.monitor_combo.currentData() or "",
            "presenter_monitor": self.screen().name() if self.screen() else "",
        }
        self.project.show_settings.setdefault("splash_text", self.project.name)
        try:
            self.project_manager.save(self.project, path)
            self._project_dirty = False
            self.statusBar().showMessage(tr("Проект сохранён: {p0}", p0=self.project.path.name))
            return True
        except StorageError as exc:
            self._warning(str(exc))
            return False

    def _show_help(self) -> None:
        QMessageBox.information(
            self,
            tr("Горячие клавиши"),
            tr(
                "F5 — начать с первого слайда\nShift+F5 — начать с выбранного\n→ / ↓ / Space / PageDown — вперёд\n← / ↑ / PageUp — назад\nHome / End — первый / последний\nЦифры + Enter — перейти к номеру\nEsc — отменить номер или завершить показ\nB / W — чёрный / белый экран (повтор — вернуть слайд)\nCtrl+O — открыть презентацию / изображение / видео\nCtrl+S — сохранить заметки\nCtrl+N — редактор заметок\nCtrl+PageDown / PageUp — следующий / предыдущий файл\nCtrl+Enter — открыть выбранный файл\nCtrl+L — очередь\nCtrl+Shift+S — сохранить проект\n\nВ полях ввода навигация слайдов отключена.\nПри одном мониторе аудитория отображается в обычном окне."
            ),
        )

    def dragEnterEvent(self, event: object) -> None:
        if any(
            (url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in self.queue.SUPPORTED)
            or is_canva_url(url.toString())
            for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()

    def dropEvent(self, event: object) -> None:
        paths = [
            url.toLocalFile() if url.isLocalFile() else url.toString()
            for url in event.mimeData().urls()
            if url.isLocalFile() or is_canva_url(url.toString())
        ]
        added = self.queue.add(paths, self.backend_status.preference.currentData())
        if added:
            self.load_item(added[0].id)
            event.acceptProposedAction()

    def showEvent(self, event: object) -> None:
        super().showEvent(event)
        if not self._screen_connected and self.windowHandle():
            self.windowHandle().screenChanged.connect(lambda _: self._refresh_monitors())
            self._screen_connected = True

    def closeEvent(self, event: object) -> None:
        if (
            self._close_waiting
            and self.backend_manager.services is not None
            and not self.backend_manager.services.finished
        ):
            event.ignore()
            return
        if self._closing:
            event.accept()
            return
        if not self.save_notes():
            self._warning(
                tr(
                    "Заметки не сохранены. Освободите место или восстановите доступ к AppData, затем повторите сохранение. Окно остаётся открытым."
                )
            )
            event.ignore()
            return
        if not self._confirm_project_replace():
            event.ignore()
            return
        if not self._save_settings() and not self.settings.read_only:
            self._warning(tr("Не удалось сохранить настройки. Заметки сохранены."))
        self._closing = True
        self.native_input.close()
        self.autosave.stop()
        self.render_debounce.stop()
        self.clock_tick.stop()
        self.presentation.stop()
        self.preloader.close()
        self.slides.bind_backend(None)
        self.renderer.close()
        self.backend_manager.close()
        self.audience.deleteLater()
        QApplication.instance().removeEventFilter(self.keyboard)
        if self.backend_manager.services is not None and not self.backend_manager.services.finished:
            self._close_waiting = True
            self.statusBar().showMessage(tr("Завершение работы внешних движков…"))
            event.ignore()
            QTimer.singleShot(100, self._finish_shutdown)
        else:
            event.accept()

    def _finish_shutdown(self) -> None:
        if self.backend_manager.services is None or self.backend_manager.services.finished:
            self._close_waiting = False
            self.close()
        else:
            QTimer.singleShot(100, self._finish_shutdown)
