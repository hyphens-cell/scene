# Contributing / Разработка

[English README](README.md) · [README на русском](README.ru.md)

## English

Use Windows and Python 3.12 x64. Install the locked dependencies and the editable package as described in the README. Run Ruff and pytest before submitting changes. Keep UI text available in both languages and preserve existing user data formats and Windows application IDs.

### Layout

- `src/pdf_presenter/ui`: Qt presenter window, queue, notes and player controls.
- `core`: event projects, settings, PDF rendering, media validation and audience display handoff.
- `backends`: common interface for PDF, images, video, Office and Canva.
- `services`: isolated Office STA workers, WebView2 worker, conversion and native-window ownership.
- `i18n.py`, `resources/locales/en.json`: Russian source strings and English catalog.
- `tests`: default offscreen regression tests and explicitly enabled native integration tests.
- `installer`, `scripts`, `PDFPresenter.spec`: Windows packaging and verification.

### Translations

Wrap application-owned text in `tr("Русский текст")`; add the matching English entry to `en.json`. Use named placeholders, for example `tr("Видео {number}", number=identifier)`. Preserve placeholder names, conversion flags and format specifications. Never translate notes, filenames, URLs, stable backend IDs or JSON keys. Avoid translating labels at module import time; defer until a widget or backend is created.

The selected language is saved in `settings.json` and applies on restart. `SCENE_LANGUAGE` overrides it and propagates to spawned workers. Qt standard button translations are loaded separately; Windows/Office/browser content may follow the system or service language. `tests/test_i18n.py` checks catalog coverage, formatting, UI behavior, persistence and worker inheritance.

### Native checks

Default tests do not launch installed Office or live Canva. Native runs require an interactive Windows desktop and appropriate runtimes. Set `QT_QPA_PLATFORM=windows` explicitly for them.

- `PDFPRESENTER_POWERPOINT_TESTS=1`: installed PowerPoint integration.
- `PDFPRESENTER_LIBREOFFICE`: full path to an installed `soffice.com`/`soffice.exe` for conversion tests.
- `SCENE_NATIVE_MEDIA_TESTS=1`: native standalone media tests; generate fixtures first with `scripts/make_media_fixture.py` (see its `--help`; use `--tone-gain 0` for silent tests).
- `SCENE_CANVA_NATIVE=1`: WebView2 tests. Set `SCENE_CANVA_URLS` to space-separated public test links with at least five slides. For video controls, set `SCENE_CANVA_VIDEO_URL` to your own publicly viewable deck with a video.

Never commit real event presentations, private links or notes. The committed Office fixtures contain five generated slides and synthetic notes; author metadata is anonymized. Regeneration via `scripts/make_office_fixture.py tests/fixtures` requires PowerPoint; inspect author metadata before sharing regenerated files.

Do not terminate foreign Office processes, change global audio/display settings or save source decks during tests. Installer verification should use `scripts/test_setup.ps1 -Isolated`. Record skipped native checks separately from passed unit tests.

### CI and publication

`.github/workflows/checks.yml` runs on Windows with read-only repository permissions. It follows the documented [checkout](https://github.com/actions/checkout), [setup-python](https://github.com/actions/setup-python) and [upload-artifact](https://github.com/actions/upload-artifact) usage. CI does not sign, install or publish app releases. License selection remains with the project owner.

## Русский

Используйте Windows и Python 3.12 x64. Установка окружения описана в README. Перед изменениями запускайте Ruff и pytest. Все пользовательские тексты должны иметь RU/EN варианты; сохраняйте совместимость данных и идентификаторов приложения Windows.

### Структура

- `ui`: окно докладчика Qt, очередь, заметки и плеер.
- `core`: проекты, настройки, PDF, проверка материалов и передача экрана аудитории.
- `backends`: общий интерфейс PDF, изображений, видео, Office и Canva.
- `services`: изолированные Office STA-процессы, WebView2, конвертация и управление собственными окнами.
- `i18n.py`, `resources/locales/en.json`: русские исходные строки и английский словарь.
- `tests`: обычные тесты без окон и явно включаемые нативные проверки.
- `installer`, `scripts`, `PDFPresenter.spec`: сборка и проверка Windows.

### Переводы

Оборачивайте текст приложения в `tr("Русский текст")` и добавляйте перевод в `en.json`. Для переменных используйте именованные параметры: `tr("Видео {number}", number=identifier)`. Имена параметров, флаги и форматирование должны совпадать. Не переводите заметки, имена файлов, ссылки, идентификаторы движков и ключи JSON. Перевод выполняйте при создании виджета или движка, а не при импорте модуля.

Язык сохраняется в `settings.json` и применяется после перезапуска. `SCENE_LANGUAGE` переопределяет его и передаётся помощникам. Стандартные кнопки Qt переводятся отдельно; Windows, Office и содержимое браузера могут использовать язык системы или сервиса. `tests/test_i18n.py` проверяет словарь, параметры, интерфейс, сохранение и наследование языка.

### Нативные проверки

Обычные тесты не запускают установленный Office или живую Canva. Для нативных тестов нужны интерактивный рабочий стол и соответствующие программы. Явно задайте `QT_QPA_PLATFORM=windows`.

- `PDFPRESENTER_POWERPOINT_TESTS=1`: интеграция с PowerPoint.
- `PDFPRESENTER_LIBREOFFICE`: полный путь к `soffice.com`/`soffice.exe` для конвертации.
- `SCENE_NATIVE_MEDIA_TESTS=1`: отдельные видео; сначала создайте материалы через `scripts/make_media_fixture.py` (параметры — через `--help`; `--tone-gain 0` убирает звук теста).
- `SCENE_CANVA_NATIVE=1`: проверки WebView2. В `SCENE_CANVA_URLS` укажите публичные тестовые ссылки через пробел, минимум пять слайдов. В `SCENE_CANVA_VIDEO_URL` — свою публичную презентацию с видео.

Не добавляйте в Git реальные мероприятия, личные ссылки и заметки. Файлы Office в тестах содержат пять искусственных слайдов с тестовыми заметками, автор обезличен. Пересоздание через `scripts/make_office_fixture.py tests/fixtures` требует PowerPoint; перед публикацией проверьте метаданные автора.

Не закрывайте чужие процессы Office, не меняйте общие настройки звука/мониторов и не сохраняйте исходные презентации во время тестов. Установщик проверяйте с `scripts/test_setup.ps1 -Isolated`. Пропущенные нативные проверки указывайте отдельно от прошедших тестов.

### CI и публикация

`.github/workflows/checks.yml` запускает проверки Windows с доступом только на чтение репозитория. CI не подписывает, не устанавливает и не публикует релизы приложения. Лицензию выбирает владелец проекта.
