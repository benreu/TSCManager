"""Small Qt helpers the window and dialogs share."""

from PySide2.QtCore import Qt
from PySide2.QtGui import QImage, QPixmap


def pixmap(image, max_width: int = 0, max_height: int = 0) -> QPixmap:
    """A QPixmap of a PIL image, scaled down (never up) to fit within the
    limits given. Scaled without smoothing, so a 1-bit picture still shows
    its dots."""
    grey = image.convert('L')
    data = grey.tobytes()
    qimage = QImage(data, grey.width, grey.height, grey.width,
                    QImage.Format_Grayscale8).copy()
    result = QPixmap.fromImage(qimage)
    if (max_width and result.width() > max_width) or (
            max_height and result.height() > max_height):
        result = result.scaled(max_width or result.width(),
                               max_height or result.height(),
                               Qt.KeepAspectRatio, Qt.FastTransformation)
    return result


ERROR_STYLE = "color: #b00020;"


def say(label, text: str, error: bool = False) -> None:
    """Put a message on a label, in red when it is a failure."""
    label.setStyleSheet(ERROR_STYLE if error else "")
    label.setText(text)
