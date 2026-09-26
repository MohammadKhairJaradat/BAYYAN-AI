"""Small signature checks for files accepted by the public upload routes."""


def matches_image_or_pdf(data: bytes, extension: str) -> bool:
    if extension in {"jpg", "jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if extension == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == "pdf":
        return data.startswith(b"%PDF-")
    if extension == "webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False
