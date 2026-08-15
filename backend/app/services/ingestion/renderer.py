from dataclasses import dataclass
from io import BytesIO

import fitz
from PIL import Image, ImageOps

from app.services.ingestion.files import ValidatedFile


@dataclass(frozen=True)
class RenderedPage:
    page_number: int
    png_bytes: bytes
    width: int
    height: int
    supplemental_text: str | None


class DocumentRenderer:
    def __init__(self, dpi: int = 200) -> None:
        self.dpi = dpi

    def render(self, source: ValidatedFile) -> list[RenderedPage]:
        if source.source_type == "pdf":
            return self._render_pdf(source.content)
        return [self._render_image(source.content)]

    def _render_pdf(self, content: bytes) -> list[RenderedPage]:
        document = fitz.open(stream=content, filetype="pdf")
        pages: list[RenderedPage] = []
        scale = self.dpi / 72
        matrix = fitz.Matrix(scale, scale)
        for index, page in enumerate(document):
            pixmap = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB)
            text = page.get_text("text").strip()
            pages.append(
                RenderedPage(
                    page_number=index + 1,
                    png_bytes=pixmap.tobytes("png"),
                    width=pixmap.width,
                    height=pixmap.height,
                    supplemental_text=text or None,
                )
            )
        document.close()
        return pages

    def _render_image(self, content: bytes) -> RenderedPage:
        with Image.open(BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            output = BytesIO()
            image.save(output, "PNG", optimize=True)
            return RenderedPage(1, output.getvalue(), image.width, image.height, None)

