import logging
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from .base import ArtistImageProvider

class GeneratedArtistImageProvider(ArtistImageProvider):
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @property
    def name(self):
        return "generated"

    def get_artist_images(self, artist_name, mbid=None, external_ids=None):
        # Generate an image with initials and a gradient/solid color
        try:
            img_size = (640, 640)
            # Use a color based on the artist name
            bg_color = self._get_color_for_name(artist_name)
            
            img = Image.new('RGB', img_size, color=bg_color)
            draw = ImageDraw.Draw(img)
            
            # Draw initials
            initials = self._get_initials(artist_name)
            # Try to load a font, fallback to default
            try:
                # This might fail if the font is not found on the system
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 300)
            except:
                font = ImageFont.load_default()
            
            # Position text in center
            # In newer Pillow version textbbox is preferred over textsize
            if hasattr(draw, 'textbbox'):
                bbox = draw.textbbox((0, 0), initials, font=font)
                w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            else:
                w, h = draw.textsize(initials, font=font)
                
            draw.text(((img_size[0]-w)/2, (img_size[1]-h)/2), initials, fill=(255, 255, 255), font=font)
            
            # Save to buffer
            buf = BytesIO()
            img.save(buf, format='JPEG')
            image_data = buf.getvalue()
            
            # We return a special 'data' field or similar, 
            # but our provider interface expects a URL.
            # I'll modify the fetcher to handle 'image_data' directly if present.
            
            return [{
                'source': self.name,
                'source_id': 'generated',
                'url': None,
                'image_data': image_data,
                'width': 640,
                'height': 640,
                'confidence': 10,
                'metadata': {'artist_name': artist_name}
            }]
        except Exception as e:
            self.logger.error(f"Error generating fallback image: {e}")
            return []

    def _get_color_for_name(self, name):
        import hashlib
        h = hashlib.md5(name.encode()).hexdigest()
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        return (r, g, b)

    def _get_initials(self, name):
        parts = name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        elif len(parts) == 1:
            return parts[0][:2].upper()
        return "??"
