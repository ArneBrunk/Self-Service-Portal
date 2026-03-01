# --- Import Django ---
from django.conf import settings
# --- Import Sonstige Module ---
from PIL import Image
from pathlib import Path


# ---  Helper-Funktionen ---
def generate_favicon_from_logo(logo_field):
    """
    Erstellt beim Upload des Company-Logos automatisch ein favicon.ico.
    Erwartet ein ImageField (company.icon).
    """
    if not logo_field:
        return None

    logo_path = Path(logo_field.path)

    # Zielverzeichnis
    favicon_dir = Path(settings.MEDIA_ROOT) / "favicon"
    favicon_dir.mkdir(parents=True, exist_ok=True)
    favicon_path = favicon_dir / "favicon.ico"

    try:
        img = Image.open(logo_path).convert("RGBA")
        size = min(img.size)
        img = img.crop((
            (img.width - size) // 2,
            (img.height - size) // 2,
            (img.width + size) // 2,
            (img.height + size) // 2
        ))

        # auf typische Favicon-Größen skalieren
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128)]

        img.save(favicon_path, format="ICO", sizes=sizes)

        return str(favicon_path)
    except Exception as e:
        print(f"Favicon generation failed: {e}")
        return None
