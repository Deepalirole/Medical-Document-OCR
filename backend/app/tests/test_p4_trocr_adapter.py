import io
import math
import sys
import types

import pytest
from PIL import Image

from app.api.dependencies import get_htr_engine
from app.core.config import Settings
from app.core.errors import AppError
from app.services.htr.trocr import DEFAULT_MODEL, TrOCREngine
from app.services.htr.unconfigured import UnconfiguredHTREngine


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (200, 60), "white").save(buffer, format="PNG")
    return buffer.getvalue()


class FakeTensor:
    """Minimal stand-in for the one torch surface the adapter actually touches."""

    def __init__(self, values):
        self.values = list(values)

    def __getitem__(self, index):
        if isinstance(index, FakeTensor):  # boolean mask, as torch.isfinite returns
            return FakeTensor([value for value in self.values if math.isfinite(value)])
        return FakeTensor(self.values) if index == 0 else FakeTensor([])

    def numel(self):
        return len(self.values)

    def mean(self):
        return sum(self.values) / len(self.values)


class FakeGeneration:
    def __init__(self, sequences, scores=None):
        self.sequences = sequences
        self.scores = scores


class FakeProcessor:
    def __init__(self, text):
        self.text = text
        self.seen_images = []

    def __call__(self, images, return_tensors=None):
        self.seen_images.append(images.size)
        return types.SimpleNamespace(pixel_values="pixels")

    def batch_decode(self, sequences, skip_special_tokens=True):
        return [self.text]


class FakeModel:
    def __init__(self, generation, transitions=None, fail=None):
        self.generation = generation
        self.transitions = transitions
        self.fail = fail
        self.generate_kwargs = None
        self.eval_called = False

    def eval(self):
        self.eval_called = True

    def generate(self, pixel_values, **kwargs):
        self.generate_kwargs = kwargs
        if self.fail:
            raise self.fail
        return self.generation

    def compute_transition_scores(self, sequences, scores, normalize_logits=True):
        if self.transitions is None:
            raise RuntimeError("transition scores unavailable")
        return [FakeTensor(self.transitions)]


def install_fake_stack(monkeypatch, processor, model, loader_error=None):
    torch_module = types.ModuleType("torch")

    class NoGrad:
        def __enter__(self):
            return None

        def __exit__(self, *args):
            return False

    torch_module.no_grad = NoGrad
    torch_module.isfinite = lambda tensor: tensor
    torch_module.exp = lambda value: __import__("math").exp(value)

    transformers_module = types.ModuleType("transformers")

    class Processor:
        @staticmethod
        def from_pretrained(name):
            if loader_error:
                raise loader_error
            return processor

    class Model:
        @staticmethod
        def from_pretrained(name):
            if loader_error:
                raise loader_error
            return model

    transformers_module.TrOCRProcessor = Processor
    transformers_module.VisionEncoderDecoderModel = Model
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "transformers", transformers_module)


def test_adapter_is_unconfigured_without_transformers(monkeypatch):
    original = __import__

    def raise_import(name, *args, **kwargs):
        if name in {"torch", "transformers"}:
            raise ImportError(f"no {name}")
        return original(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", raise_import)
    engine = TrOCREngine()
    assert engine.available is False
    assert engine.health()["status"] == "HTR_NOT_CONFIGURED"
    with pytest.raises(AppError) as error:
        engine.extract(png_bytes())
    assert error.value.code == "HTR_NOT_CONFIGURED"
    assert error.value.status_code == 503


def test_disabled_adapter_stays_inert():
    engine = TrOCREngine(enabled=False)
    assert engine.available is False
    with pytest.raises(AppError) as error:
        engine.extract(png_bytes())
    assert error.value.code == "HTR_NOT_CONFIGURED"


def test_adapter_emits_canonical_evidence_without_fabricating_boxes(monkeypatch):
    processor = FakeProcessor("Cap Omeprazole 20 mg")
    model = FakeModel(FakeGeneration(sequences=[[1, 2]], scores=[0.1]), transitions=[-0.1, -0.2])
    install_fake_stack(monkeypatch, processor, model)

    result = TrOCREngine().extract(png_bytes())

    assert result.provider == "trocr"
    assert result.provider_version == DEFAULT_MODEL
    assert result.raw_text == "Cap Omeprazole 20 mg"
    assert [token.text for token in result.tokens] == ["Cap", "Omeprazole", "20", "mg"]
    assert all(token.bbox is None for token in result.tokens)
    assert result.metadata["bounding_boxes_available"] is False
    assert result.metadata["line_level"] is True


def test_confidence_comes_from_real_generation_scores(monkeypatch):
    processor = FakeProcessor("Cap Omeprazole")
    model = FakeModel(FakeGeneration(sequences=[[1]], scores=[0.1]), transitions=[-0.1, -0.3])
    install_fake_stack(monkeypatch, processor, model)
    result = TrOCREngine().extract(png_bytes())
    assert result.confidence == pytest.approx(0.8187, abs=1e-3)
    assert all(token.confidence == result.confidence for token in result.tokens)


def test_missing_generation_scores_yield_no_confidence_rather_than_a_guess(monkeypatch):
    processor = FakeProcessor("Cap Omeprazole")
    model = FakeModel(FakeGeneration(sequences=[[1]], scores=None))
    install_fake_stack(monkeypatch, processor, model)
    result = TrOCREngine().extract(png_bytes())
    assert result.confidence is None
    assert all(token.confidence is None for token in result.tokens)


def test_unavailable_transition_scores_degrade_to_no_confidence(monkeypatch):
    processor = FakeProcessor("Cap Omeprazole")
    model = FakeModel(FakeGeneration(sequences=[[1]], scores=[0.2]), transitions=None)
    install_fake_stack(monkeypatch, processor, model)
    result = TrOCREngine().extract(png_bytes())
    assert result.raw_text == "Cap Omeprazole"
    assert result.confidence is None


def test_inference_crash_is_reported_as_htr_failed(monkeypatch):
    processor = FakeProcessor("ignored")
    model = FakeModel(None, fail=RuntimeError("cuda oom"))
    install_fake_stack(monkeypatch, processor, model)
    with pytest.raises(AppError) as error:
        TrOCREngine().extract(png_bytes())
    assert error.value.code == "HTR_FAILED"
    assert error.value.status_code == 502


def test_weight_load_failure_is_reported_as_not_configured(monkeypatch):
    install_fake_stack(monkeypatch, None, None, loader_error=OSError("weights missing"))
    with pytest.raises(AppError) as error:
        TrOCREngine("microsoft/trocr-large-handwritten").extract(png_bytes())
    assert error.value.code == "HTR_NOT_CONFIGURED"
    assert "trocr-large-handwritten" in error.value.message


def test_model_is_loaded_once_and_set_to_eval(monkeypatch):
    processor = FakeProcessor("Cap")
    model = FakeModel(FakeGeneration(sequences=[[1]], scores=None))
    install_fake_stack(monkeypatch, processor, model)
    engine = TrOCREngine(max_new_tokens=64)
    engine.extract(png_bytes())
    engine.extract(png_bytes())
    assert model.eval_called is True
    assert model.generate_kwargs["max_new_tokens"] == 64
    assert len(processor.seen_images) == 2


def test_htr_provider_setting_selects_the_engine_and_defaults_stay_inert():
    assert Settings().htr_provider == ""
    assert isinstance(get_htr_engine(Settings()), UnconfiguredHTREngine)
    engine = get_htr_engine(
        Settings(htr_provider="trocr", htr_model="microsoft/trocr-small-handwritten")
    )
    assert isinstance(engine, TrOCREngine)
    assert engine.model_name == "microsoft/trocr-small-handwritten"


def test_blank_model_name_falls_back_to_the_default_checkpoint():
    assert get_htr_engine(Settings(htr_provider="trocr")).model_name == DEFAULT_MODEL
