import io
import sys
import types

import pytest
from PIL import Image

from app.api.dependencies import get_ocr_engine
from app.core.config import Settings
from app.core.errors import AppError
from app.services.ocr.paddle import PaddleOCREngine
from app.services.ocr.tesseract import TesseractEngine

PAGE = [
    [[[10, 12], [110, 12], [110, 40], [10, 40]], ("Augmentin", 0.97)],
    [[[10, 50], [90, 50], [90, 78], [10, 78]], ("625 mg", 0.88)],
    [[[10, 90], [60, 90], [60, 110], [10, 110]], ("   ", 0.40)],
]


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (120, 120), "white").save(buffer, format="PNG")
    return buffer.getvalue()


class FakeReader:
    def __init__(self, result, **kwargs):
        self.result = result
        self.kwargs = kwargs
        self.calls = []

    def ocr(self, image, cls=True):
        self.calls.append((getattr(image, "shape", None), cls))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def install_fake_paddle(monkeypatch, result, version="2.9.0", constructor=None):
    module = types.ModuleType("paddleocr")
    module.__version__ = version
    created: dict = {}

    def factory(**kwargs):
        if constructor is not None:
            return constructor(kwargs)
        reader = FakeReader(result, **kwargs)
        created["reader"] = reader
        return reader

    module.PaddleOCR = factory
    monkeypatch.setitem(sys.modules, "paddleocr", module)
    return created


def test_adapter_reports_unconfigured_when_the_package_is_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "paddleocr", None)
    engine = PaddleOCREngine()

    def raise_import(name, *args, **kwargs):
        if name == "paddleocr":
            raise ImportError("no paddleocr")
        return original(name, *args, **kwargs)

    original = __import__
    monkeypatch.setattr("builtins.__import__", raise_import)

    assert engine.available is False
    assert engine.health() == {
        "provider": "paddleocr",
        "configured": False,
        "language": "en",
        "status": "OCR_NOT_CONFIGURED",
    }
    with pytest.raises(AppError) as error:
        engine.extract(png_bytes())
    assert error.value.code == "OCR_NOT_CONFIGURED"
    assert error.value.status_code == 503


def test_disabled_adapter_never_imports_the_dependency():
    engine = PaddleOCREngine(enabled=False)
    assert engine.available is False
    with pytest.raises(AppError) as error:
        engine.extract(png_bytes())
    assert error.value.code == "OCR_NOT_CONFIGURED"


def test_adapter_emits_canonical_evidence(monkeypatch):
    install_fake_paddle(monkeypatch, [PAGE])
    result = PaddleOCREngine().extract(png_bytes())

    assert result.provider == "paddleocr"
    assert result.provider_version == "2.9.0"
    assert result.raw_text == "Augmentin 625 mg"
    assert [token.text for token in result.tokens] == ["Augmentin", "625 mg"]
    assert [token.sequence_index for token in result.tokens] == [0, 1]
    assert result.tokens[0].confidence == 0.97
    assert result.confidence == pytest.approx((0.97 + 0.88) / 2)
    assert result.metadata == {"language": "en", "angle_classification": True}


def test_bounding_boxes_become_axis_aligned(monkeypatch):
    install_fake_paddle(monkeypatch, [PAGE])
    box = PaddleOCREngine().extract(png_bytes()).tokens[0].bbox
    assert (box.x1, box.y1, box.x2, box.y2) == (10, 12, 110, 40)


def test_flat_and_paged_result_shapes_are_both_handled(monkeypatch):
    install_fake_paddle(monkeypatch, PAGE)
    flat = PaddleOCREngine().extract(png_bytes())
    install_fake_paddle(monkeypatch, [PAGE])
    paged = PaddleOCREngine().extract(png_bytes())
    assert flat.raw_text == paged.raw_text == "Augmentin 625 mg"


def test_a_page_with_no_text_yields_empty_evidence_not_an_error(monkeypatch):
    install_fake_paddle(monkeypatch, [None])
    result = PaddleOCREngine().extract(png_bytes())
    assert result.raw_text == ""
    assert result.tokens == []
    assert result.confidence is None


def test_provider_crash_is_reported_as_ocr_failed(monkeypatch):
    install_fake_paddle(monkeypatch, RuntimeError("inference failed"))
    with pytest.raises(AppError) as error:
        PaddleOCREngine().extract(png_bytes())
    assert error.value.code == "OCR_FAILED"
    assert error.value.status_code == 502


def test_model_initialisation_failure_is_reported_as_not_configured(monkeypatch):
    def broken(_kwargs):
        raise OSError("model weights unavailable")

    install_fake_paddle(monkeypatch, None, constructor=broken)
    with pytest.raises(AppError) as error:
        PaddleOCREngine().extract(png_bytes())
    assert error.value.code == "OCR_NOT_CONFIGURED"


def test_constructor_falls_back_when_show_log_is_unsupported(monkeypatch):
    attempts: list[dict] = []

    def constructor(kwargs):
        attempts.append(kwargs)
        if "show_log" in kwargs:
            raise TypeError("unexpected keyword argument 'show_log'")
        return FakeReader([PAGE], **kwargs)

    install_fake_paddle(monkeypatch, None, constructor=constructor)
    result = PaddleOCREngine().extract(png_bytes())
    assert result.raw_text == "Augmentin 625 mg"
    assert len(attempts) == 2 and "show_log" not in attempts[1]


def test_language_and_angle_settings_reach_the_reader(monkeypatch):
    created = install_fake_paddle(monkeypatch, [PAGE])
    PaddleOCREngine(language="hi", use_angle_classification=False).extract(png_bytes())
    reader = created["reader"]
    assert reader.kwargs["lang"] == "hi"
    assert reader.kwargs["use_angle_cls"] is False
    assert reader.calls[0][1] is False


def test_reader_is_initialised_once_and_reused(monkeypatch):
    constructions: list[dict] = []

    def constructor(kwargs):
        constructions.append(kwargs)
        return FakeReader([PAGE], **kwargs)

    install_fake_paddle(monkeypatch, None, constructor=constructor)
    engine = PaddleOCREngine()
    engine.extract(png_bytes())
    engine.extract(png_bytes())
    assert len(constructions) == 1


def test_ocr_provider_setting_selects_the_engine_without_changing_the_default():
    assert Settings().ocr_provider == "tesseract"
    assert isinstance(get_ocr_engine(Settings(ocr_provider="tesseract")), TesseractEngine)
    paddle = get_ocr_engine(
        Settings(ocr_provider="paddleocr", paddleocr_language="hi")
    )
    assert isinstance(paddle, PaddleOCREngine)
    assert paddle.language == "hi"
