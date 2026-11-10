# Scene / Сцена

[English](README.md) · [Русский](README.ru.md)

**[Download latest Windows installer](https://github.com/hyphens-cell/scene/releases/latest/download/Scene-Setup-x64.exe)** · [All releases and SHA-256 checksums](https://github.com/hyphens-cell/scene/releases/latest)

<img src="src/pdf_presenter/resources/icons/scene.png" alt="Scene app icon" width="112">

**Scene** is a Windows presenter app for PDF, PowerPoint, Canva, images and video. Keep notes and controls on the presenter display while the audience sees the presentation.

**Version 2.3.0** includes **Russian and English** interfaces. Select **Язык / Language → Русский / English**, then restart the app. Russian is the default. Selecting a language does not interrupt a show or translate your notes and filenames. The Windows installer is `Scene-Setup-2.3.0-x64.exe`.

## Features

- One reorderable queue for presentations, images, videos and Canva links; folder import and drag and drop.
- Current/next slide previews, thumbnails, slide-number navigation, private notes, timer and clock.
- Video player: play/pause, stop, seek, volume and loop, depending on the engine.
- Image/video scaling: fit, fill, stretch, original size or custom 1–1000%; drag the enlarged preview to pan.
- Black/white screen, event splash screen and hold frame; audience cover during engine switches.
- Event projects (`.pdfpresenter`) with relative local paths, queue order and media settings.
- Separate audience window, with a regular windowed preview when only one display is available.

## Requirements and limitations

Windows 10 version 1809 or newer, or Windows 11, **x64**. Packaged builds include Python, Qt, MuPDF and the standalone player libraries. Separate codec packs are not required; a container extension does not guarantee support for every codec inside it.

| Content | Additional requirements | Limitations |
| --- | --- | --- |
| PDF | None | Static slides; password entry supported |
| Images | None | Qt formats including PNG, JPEG, BMP, WebP, TIFF, GIF and SVG; first frame of animated/multipage images |
| Standalone video | None | MP4, MKV, AVI, MOV, WebM and more; codec-dependent playback |
| Native PPT/PPTX | Microsoft PowerPoint | Native animations/media; embedded video volume control unavailable |
| PPT/PPTX compatibility | LibreOffice or a same-name PDF beside the presentation | PDF conversion removes animations/audio/video; native Impress is experimental |
| Canva | Internet, a public viewing link, WebView2 Runtime, .NET Framework 4.6.2+ | No login, DRM or third-party iframe video support; no next-slide preview or imported Canva notes |

Local files work offline; Canva requires internet. Install WebView2 through **Help → WebView2 for Canva** if needed. It is not bundled in Setup. Canva is shown in an isolated embedded browser; Scene does not edit the design or its sharing permissions. Viewer updates may affect compatibility.

PowerPoint loop is implemented but still needs verification during real playback. Standalone and Canva looping were verified before localization. Native audio/display/Office behavior must also be tested on the target machine.

## Start a show

1. Run `PDFPresenter.exe` from the complete portable folder, or install `Scene-Setup-<version>-x64.exe`. The executable name is retained for compatibility.
2. Click **Add media**, drag files into the window, or use **Canva link**. Canva editor links open in viewing mode.
3. Select the audience display. Use **Extend** in Windows (Win+P) for two monitors.
4. Press **F5** to start from the beginning, or **Shift+F5** from the selected slide.
5. Control video below the preview. **Loop** repeats the selected video; standalone looping suspends automatic queue advancement. Volume changes affect the video, not Windows master volume.
6. Press **Esc** or **End show** to finish. Save an event with **Ctrl+Shift+S**.

Standalone scale, pan, volume and loop are saved in the project. Embedded Canva/PowerPoint loop applies to the current session. Notes stay on the presenter display and are autosaved.

| Shortcut | Action |
| --- | --- |
| → / ↓ / Space / PageDown | Next slide or native animation step |
| ← / ↑ / PageUp | Previous slide |
| Home / End | First / last slide |
| Digits + Enter | Jump to slide number |
| B / W | Black / white screen; press again to return |
| Ctrl+O | Open media |
| Ctrl+S / Ctrl+N | Save notes / focus notes editor |
| Ctrl+PageDown / Ctrl+PageUp | Next / previous queue item |
| Ctrl+Enter / Ctrl+L | Open selected item / focus queue |

Slide navigation is disabled in text fields. F5/Shift+F5 reset the timer; Esc cancels number entry before ending the show.

## Development

Python **3.12 x64**, Windows, PowerShell from the repository root:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e ".[dev]"
.venv\Scripts\python.exe main.py
```

The lock file records the verified Windows environment; `pyproject.toml` declares supported ranges. `SCENE_LANGUAGE=en` or `ru` overrides the saved language for that process and its workers.

```powershell
.venv\Scripts\python.exe -m ruff check src tests scripts
.venv\Scripts\python.exe -m ruff format --check src tests scripts
.venv\Scripts\python.exe -m pytest -q
```

Default tests run offscreen without Office, accounts or internet. Native tests are opt-in; see [CONTRIBUTING.md](CONTRIBUTING.md). GitHub Actions runs Windows lint, RU/EN tests and a wheel build; it does not publish releases.

Run `build.bat` for PyInstaller, then `build_setup.bat` for Inno Setup. Keep all of `dist/PDFPresenter`, including `_internal`. New builds include both READMEs.

```powershell
.\build_setup.bat -RebuildApp
.\build_setup.bat -InnoCompiler "C:\Program Files\Inno Setup 7\ISCC.exe"
pwsh -File scripts/test_setup.ps1 -Isolated
```

Setup can download the official signed Inno Setup 7.1.1 compiler into `artifacts/tooling`; first-time preparation needs internet. App installers are per-user and currently unsigned. The isolated setup test uses a separate test AppId and protects the existing installation.

## Data and publication

Settings, notes and logs remain in `%APPDATA%\PDFPresenter`. Existing project formats are preserved. Projects reference media rather than embedding it; keep the referenced files when moving an event.

Builds, logs, credentials, local work records and user projects are excluded from Git. Committed Office fixtures are synthetic, with anonymized author metadata. Live Canva tests receive links through environment variables.

[Contributor guide](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [GitHub preparation](docs/github.md)

A project license has **not yet been selected**; no open-source license grant is implied. Dependencies retain their own licenses.
