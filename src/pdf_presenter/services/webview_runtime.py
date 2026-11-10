"""Read-only runtime detection; Canva never falls back to Internet Explorer."""

from pdf_presenter.i18n import tr


def require_webview2():
    import winreg

    key = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(root, key, 0, winreg.KEY_READ | view) as handle:
                    version = str(winreg.QueryValueEx(handle, "pv")[0])
                    if version and version != "0.0.0.0":
                        return
            except OSError:
                pass
    raise RuntimeError(
        tr(
            "Для Canva нужен Microsoft Edge WebView2 Runtime. Откройте «Справка → WebView2 для Canva» и установите Evergreen Runtime x64. PDF, изображения и отдельные видео работают без него."
        )
    )
