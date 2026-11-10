"""Create owned PowerPoint integration fixtures, without changing user documents."""

import argparse
from pathlib import Path


def create_fixture(directory: Path) -> None:
    import pythoncom
    import win32com.client

    from pdf_presenter.services.native_window import running_office_pids

    directory.mkdir(parents=True, exist_ok=True)
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    previous = running_office_pids("POWERPNT.EXE")
    app = presentation = None
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        presentation = app.Presentations.Add(0)
        for index in range(1, 6):
            slide = presentation.Slides.Add(index, 12)
            title = slide.Shapes.AddTextbox(1, 70, 60, 600, 100)
            title.TextFrame.TextRange.Text = f"PDF Presenter integration — slide {index}"
            title.TextFrame.TextRange.Font.Size = 28
            if index == 2:
                shape = slide.Shapes.AddShape(1, 200, 220, 200, 100)
                slide.TimeLine.MainSequence.AddEffect(shape, 1, 0, 1)
            for n in range(1, slide.NotesPage.Shapes.Count + 1):
                shape = slide.NotesPage.Shapes.Item(n)
                if shape.Type == 14 and shape.PlaceholderFormat.Type == 2:
                    shape.TextFrame.TextRange.Text = f"Speaker note {index} — private"
        presentation.BuiltInDocumentProperties.Item("Author").Value = "Scene test fixture"
        presentation.SaveAs(str(directory / "native-animation.pptx"), 24)
        presentation.SaveAs(str(directory / "legacy.ppt"), 1)
    finally:
        if presentation is not None:
            presentation.Saved = -1
            presentation.Close()
        if app is not None and not previous and app.Presentations.Count == 0:
            app.Quit()
        app = presentation = None
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    create_fixture(args.directory.resolve())
