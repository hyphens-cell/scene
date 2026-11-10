"""Owned WebView2 process. No account access, local file access or Python JS API."""

import json
import os
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pdf_presenter.i18n import tr

from ..core.canva_url import is_canva_url, normalize_canva_url


def run_canva_worker(pipe):
    window = None
    try:
        # Parent assigns this process to its cleanup job before any browser starts.
        source = normalize_canva_url(pipe.recv())
        # The presenter Play button is outside the web document. This flag applies
        # only to this owned child process; preload/cover/stop still mute and pause.
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
            os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
            + " --autoplay-policy=no-user-gesture-required"
        ).strip()
        import webview

        webview.settings.update(
            ALLOW_DOWNLOADS=False, ALLOW_FILE_URLS=False, OPEN_EXTERNAL_LINKS_IN_BROWSER=False
        )
        window = webview.create_window(
            tr("Сцена — Canva"),
            html="<html><body style='background:#000'></body></html>",
            hidden=True,
            width=1280,
            height=720,
            frameless=True,
            shadow=False,
            easy_drag=False,
            background_color="#000000",
            focus=False,
        )
        adapter = (Path(__file__).parents[1] / "resources" / "canva_adapter.js").read_text(
            encoding="utf-8"
        )

        def commands():
            try:
                if not window.events.loaded.wait(25):
                    raise RuntimeError(
                        tr("WebView2 не запустился. Установите Microsoft Edge WebView2 Runtime.")
                    )
                from Microsoft.Web.WebView2.Core import (
                    CoreWebView2CapturePreviewImageFormat,
                    CoreWebView2PermissionState,
                )
                from System import Action
                from System.IO import MemoryStream

                browser = window.native.browser

                def navigation(_, event):
                    url = str(event.Uri)
                    if url == "about:blank":
                        return
                    if not is_canva_url(url):
                        event.Cancel = True
                    elif urlsplit(url).hostname != "canva.link" and "embed" not in parse_qs(
                        urlsplit(url).query, keep_blank_values=True
                    ):
                        event.Cancel = True
                        viewer_url = normalize_canva_url(url) + "?embed"
                        browser.webview.BeginInvoke(
                            Action(lambda: browser.webview.CoreWebView2.Navigate(viewer_url))
                        )

                def popup(_, event):
                    event.Handled = True

                def permission(_, event):
                    event.State = CoreWebView2PermissionState.Deny

                def configure():
                    from webview.platforms.winforms import DwmSetWindowAttribute

                    # Square audience corners also allow occlusion-safe capture.
                    DwmSetWindowAttribute(window.native.Handle.ToInt64(), 33, 1)
                    core = browser.webview.CoreWebView2
                    core.IsMuted = True
                    core.Settings.IsWebMessageEnabled = False
                    core.Settings.AreHostObjectsAllowed = False
                    core.Settings.AreDefaultScriptDialogsEnabled = False
                    core.Settings.AreDefaultContextMenusEnabled = False
                    core.Settings.AreDevToolsEnabled = False
                    core.Settings.AreBrowserAcceleratorKeysEnabled = False
                    core.NewWindowRequested -= browser.on_new_window_request
                    core.NewWindowRequested += popup
                    core.NavigationStarting += navigation
                    core.PermissionRequested += permission

                browser.webview.Invoke(Action(configure))

                # Use the platform's native script result, with the JS/Python bridge disabled.
                def js(expression):
                    return browser.evaluate_js(expression, False)

                def call(method, *args):
                    return js(
                        "window.__sceneCanva."
                        + method
                        + "("
                        + ",".join(json.dumps(arg) for arg in args)
                        + ")"
                    )

                def muted(value):
                    browser.webview.Invoke(
                        Action(lambda: setattr(browser.webview.CoreWebView2, "IsMuted", value))
                    )

                def capture():
                    # Capture this WebView's rendering, never the desktop or another app.
                    stream = MemoryStream()
                    tasks = []
                    try:
                        browser.webview.Invoke(
                            Action(
                                lambda: tasks.append(
                                    browser.webview.CoreWebView2.CapturePreviewAsync(
                                        CoreWebView2CapturePreviewImageFormat.Png, stream
                                    )
                                )
                            )
                        )
                        deadline = time.monotonic() + 3
                        while not tasks[0].IsCompleted and time.monotonic() < deadline:
                            time.sleep(0.01)
                        if not tasks[0].IsCompleted:
                            return b""
                        tasks[0].GetAwaiter().GetResult()
                        return bytes(stream.ToArray())
                    except Exception:
                        return b""  # A preview failure must not interrupt the audience's show.
                    finally:
                        if not tasks or tasks[0].IsCompleted:
                            stream.Dispose()

                def go(index):
                    if (call("state") or {}).get("index") == index:
                        return
                    call("navigate", "goto", index)
                    end = time.monotonic() + 3
                    while time.monotonic() < end:
                        if (call("state") or {}).get("index") == index:
                            return
                        time.sleep(0.05)
                    raise RuntimeError(tr("Canva не подтвердила переход на выбранный слайд."))

                window.load_url(source)
                deadline = time.monotonic() + 50
                state = {}
                while time.monotonic() < deadline:
                    js(adapter)
                    state = call("state") or {}
                    if state.get("ready"):
                        break
                    time.sleep(0.2)
                if not state.get("ready"):
                    raise RuntimeError(
                        tr(
                            "Canva не открыла просмотр. Проверьте интернет и доступ «Все, у кого есть ссылка»."
                        )
                    )
                # Conceal the viewer controls without removing their DOM navigation state.
                call("hideControls")
                hwnd = int(window.native.Handle.ToInt64())
                pipe.send(("loaded", {**state, "hwnd": hwnd}))
                while True:
                    if not pipe.poll(0.05):
                        continue
                    request = pipe.recv()
                    if request is None:
                        break
                    method, values = request
                    try:
                        if method == "state":
                            result = call("state")
                            if values.get("preview") and isinstance(result, dict):
                                result["preview"] = capture()
                        elif method == "start":
                            # Win32 placement alone does not update WinForms' Visible
                            # state, so WebView2 may keep deferring media loading.
                            def show_native():
                                window.native.Show()
                                browser.webview.Visible = True

                            browser.webview.Invoke(Action(show_native))
                            # Re-enter the slide to replay Canva's own entry animations.
                            if state.get("count", 0) > 1:
                                go((values["index"] + 1) % state["count"])
                            go(values["index"])
                            call("start", values.get("volume", 100))
                            result = call("state")
                            muted(False)
                        elif method == "stop":
                            muted(True)
                            call("stop")
                            window.hide()
                            result = call("state")
                        elif method == "cover":
                            muted(bool(values["covered"]))
                            call("cover", values["covered"])
                            result = call("state")
                        elif method == "navigate":
                            if values["action"] == "goto":
                                go(values["index"])
                                pipe.send((method, call("state")))
                                continue
                            accepted = call("navigate", values["action"], values.get("index", 0))
                            if not accepted:
                                raise RuntimeError(
                                    tr(
                                        "Canva изменила элементы управления. Откройте ссылку повторно."
                                    )
                                )
                            result = call("state")
                        elif method == "control":
                            if not call(
                                "control", values["id"], values["action"], values.get("value", 0)
                            ):
                                raise RuntimeError(
                                    tr("Видео Canva ещё не готово или слайд изменился.")
                                )
                            result = call("state")
                        else:
                            raise ValueError("Unknown Canva command")
                        pipe.send((method, result))
                    except Exception as exc:
                        pipe.send(("command_error", {"method": method, "message": str(exc)}))
            except (EOFError, BrokenPipeError, OSError):
                pass
            except Exception as exc:
                try:
                    pipe.send(("error", str(exc)))
                except (OSError, EOFError):
                    pass
            finally:
                window.destroy()

        webview.start(commands, gui="edgechromium", private_mode=True, http_server=False)
    except Exception as exc:
        try:
            pipe.send(("error", "Canva / WebView2: " + str(exc)))
        except (OSError, EOFError):
            pass
    finally:
        pipe.close()
