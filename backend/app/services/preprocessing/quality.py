from dataclasses import asdict, dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class QualityReport:
    blur_score: float
    brightness: float
    contrast: float
    skew_angle: float
    width: int
    height: int
    low_contrast: bool
    blurry: bool

    def as_dict(self) -> dict[str, float | int | bool]:
        return asdict(self)


class ImageQualityAnalyzer:
    def analyze(self, png_bytes: bytes) -> QualityReport:
        encoded = np.frombuffer(png_bytes, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError("Image could not be decoded")
        height, width = image.shape
        blur_score = float(cv2.Laplacian(image, cv2.CV_64F).var())
        brightness = float(np.mean(image))
        contrast = float(np.std(image))
        skew_angle = self._estimate_skew(image)
        return QualityReport(
            blur_score=round(blur_score, 3),
            brightness=round(brightness, 3),
            contrast=round(contrast, 3),
            skew_angle=round(skew_angle, 3),
            width=width,
            height=height,
            low_contrast=contrast < 35,
            blurry=blur_score < 80,
        )

    @staticmethod
    def _estimate_skew(gray: np.ndarray) -> float:
        inverted = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        coordinates = np.column_stack(np.where(inverted > 0))
        if len(coordinates) < 20:
            return 0.0
        angle = float(cv2.minAreaRect(coordinates[:, ::-1].astype(np.float32))[-1])
        if angle < -45:
            angle += 90
        elif angle > 45:
            angle -= 90
        if abs(angle) > 15:
            return 0.0
        return angle

