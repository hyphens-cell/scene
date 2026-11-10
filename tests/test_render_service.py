from pdf_presenter.core.render_service import Raster, RasterCache, RenderService


def test_lru_memory_bound():
    cache = RasterCache(12)
    raster = Raster(2, 1, 6, b"123456")
    cache.put((0, 2, 1), raster)
    cache.put((1, 2, 1), raster)
    cache.get((0, 2, 1))
    cache.put((2, 2, 1), raster)
    assert cache.get((1, 2, 1)) is None
    assert cache.get((0, 2, 1)) is raster
    assert cache.used == 12
    cache.put((3, 2, 1), Raster(10, 1, 30, b"x" * 30))
    assert cache.used == 12
    cache.clear()
    assert cache.used == 0


def test_async_real_pdf_cancellation_switch_and_release(qtbot, pdf_factory):
    service = RenderService(budget=2_000_000)
    first = pdf_factory(300)
    second = pdf_factory(2, "second.pdf")
    results = []
    service.ready.connect(lambda tag, page, raster: results.append((tag, page, raster)))
    try:
        with qtbot.waitSignal(service.loaded, timeout=15000):
            service.load(str(first))
        assert service.document.page_count == 300
        for page in range(299):
            service.begin_frame()
            service.request("current", page, 800, 600)
        service.begin_frame()
        service.request("current", 299, 800, 600)
        assert service.pending_count <= 2
        qtbot.waitUntil(lambda: bool(results), timeout=15000)
        assert [(tag, page) for tag, page, _ in results] == [("current", 299)]
        assert service.cache.used <= service.cache.budget
        with qtbot.waitSignal(service.loaded, timeout=15000):
            service.load(str(second))
        assert service.cache.used == 0
        assert service.document.page_count == 2
        # A closed worker must not keep the previous document locked on Windows.
        first.rename(first.with_name("released.pdf"))
    finally:
        service.close()


def test_failed_candidate_keeps_current_document(qtbot, pdf_factory, tmp_path):
    service = RenderService()
    try:
        with qtbot.waitSignal(service.loaded, timeout=15000):
            service.load(str(pdf_factory(2)))
        original = service.document
        with qtbot.waitSignal(service.load_failed, timeout=15000):
            service.load(str(tmp_path / "missing.pdf"))
        assert service.document == original
        with qtbot.waitSignal(service.ready, timeout=15000):
            service.request("current", 1, 100, 100)
    finally:
        service.close()


def test_inflight_old_frame_never_updates_new_slide(qtbot, pdf_factory):
    service = RenderService()
    delivered = []
    service.ready.connect(lambda tag, page, raster: delivered.append(page))
    try:
        with qtbot.waitSignal(service.loaded, timeout=15000):
            service.load(str(pdf_factory(50)))
        service.request("current", 0, 4096, 4096)
        service._poll()  # Dispatch one real render; do not consume its reply yet.
        assert service._busy is not None
        service.begin_frame()
        service.request("current", 34, 400, 300)
        qtbot.waitUntil(lambda: bool(delivered), timeout=15000)
        assert delivered == [34]
    finally:
        service.close()
