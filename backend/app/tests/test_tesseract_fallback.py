from io import BytesIO

from PIL import Image, ImageDraw

from app.services.ocr.tesseract import TesseractEngine


def test_tesseract_recovers_sideways_sparse_text(monkeypatch):
    calls: list[tuple[int, str]] = []

    def fake_image_to_data(image, *, lang, config, output_type, timeout):
        calls.append((image.width, config))
        if image.width > image.height and config == "--psm 11":
            return {
                "text": ["Patient", "Evidence"],
                "conf": ["90", "80"],
                "left": [1, 10],
                "top": [2, 20],
                "width": [5, 8],
                "height": [6, 9],
            }
        return {"text": [], "conf": [], "left": [], "top": [], "width": [], "height": []}

    monkeypatch.setattr("pytesseract.image_to_data", fake_image_to_data)
    monkeypatch.setattr("pytesseract.get_tesseract_version", lambda: "test")
    image = Image.new("RGB", (200, 400), "white")
    ImageDraw.Draw(image).text((10, 10), "Patient Evidence", fill="black")
    content = BytesIO()
    image.save(content, "PNG")

    result = TesseractEngine("tesseract").extract(content.getvalue())

    assert result.raw_text == "Patient Evidence"
    assert result.metadata["rotation_degrees"] == 90
    assert result.metadata["page_segmentation_mode"] == 11
    assert calls[0][1] == "--psm 3"
