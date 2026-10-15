import io
from unittest import TestCase

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from .photos import PhotoValidationError, sanitize_image


class ImageSanitizationTests(TestCase):
    def test_reencodes_and_removes_exif(self):
        image = Image.new('RGB', (8, 9), 'green')
        exif = Image.Exif()
        exif[270] = 'private location metadata'
        stream = io.BytesIO()
        image.save(stream, format='JPEG', exif=exif)
        clean = sanitize_image(SimpleUploadedFile('proof.jpg', stream.getvalue()))
        self.assertEqual(clean['mime'], 'image/jpeg')
        self.assertEqual((clean['width'], clean['height']), (8, 9))
        self.assertFalse(Image.open(io.BytesIO(clean['content'])).getexif())

    def test_rejects_disguised_non_image(self):
        with self.assertRaises(PhotoValidationError):
            sanitize_image(SimpleUploadedFile('photo.jpg', b'<script>bad</script>'))

    def test_rejects_more_than_ten_megabytes(self):
        with self.assertRaises(PhotoValidationError):
            sanitize_image(SimpleUploadedFile('photo.png', b'x' * (10 * 1024 * 1024 + 1)))

    def test_rejects_unsupported_format(self):
        stream = io.BytesIO()
        Image.new('RGB', (8, 9)).save(stream, format='BMP')
        with self.assertRaises(PhotoValidationError):
            sanitize_image(SimpleUploadedFile('image.png', stream.getvalue()))

    def test_rejects_corrupt_png_checksum(self):
        import base64
        corrupt = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6u1QAAAAASUVORK5CYII=')
        with self.assertRaises(PhotoValidationError):
            sanitize_image(SimpleUploadedFile('broken.png', corrupt))
