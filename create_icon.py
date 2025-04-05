from PIL import Image, ImageDraw

# Create a new image with a transparent background
img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Draw a simple V shape
draw.polygon([(128, 50), (50, 200), (206, 200)], fill=(255, 255, 255, 255))

# Save the image
img.save('assets/icon.png') 