from dataclasses import dataclass

import cv2
import numpy as np

from app.services.preprocessing.quality import QualityReport


@dataclass(frozen=True)
class PreprocessedImage:
    png_bytes: bytes
    operations: list[str]


class ImagePreprocessor:
    def process(self, original_png: bytes, quality: QualityReport) -> PreprocessedImage:
        image = cv2.imdecode(np.frombuffer(original_png, np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError("Image could not be decoded")
        operations = ["grayscale"]

        if 0.5 <= abs(quality.skew_angle) <= 15:
            image = self._rotate(image, quality.skew_angle)
            operations.append("deskew")
        if quality.low_contrast:
            image = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(image)
            operations.append("contrast_enhancement")
        if quality.blurry:
            image = cv2.GaussianBlur(image, (3, 3), 0)
            operations.append("denoise")
        if min(image.shape) < 1000:
            image = cv2.resize(image, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
            operations.append("resize")

        ok, encoded = cv2.imencode(".png", image, [cv2.IMWRITE_PNG_COMPRESSION, 6])
        if not ok:
            raise ValueError("Processed image could not be encoded")
        return PreprocessedImage(encoded.tobytes(), operations)

    @staticmethod
    def _rotate(image: np.ndarray, angle: float) -> np.ndarray:
        height, width = image.shape[:2]
        transform = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
        return cv2.warpAffine(
            image,
            transform,
            (width, height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

