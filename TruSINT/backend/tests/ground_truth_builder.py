"""
ground_truth_builder.py — Generates Deterministic Ground-Truth Dataset for Retrieval Benchmarks

Constructs known-relationship test fixtures without relying on external web sources or faces:
- Base image (to be indexed in SQLite)
- Exact byte copy (expected: exact_duplicate)
- Resized copy (expected: strong_near_duplicate)
- Recompressed copy (expected: strong_near_duplicate)
- Mildly cropped copy (expected: near_duplicate)
- Visually similar pattern (expected: weak_near_duplicate or threshold boundary)
- Entirely unrelated image (expected: non_match)
- Unindexed query (expected: non_match)
"""

import os
from PIL import Image, ImageDraw


def build_ground_truth_dataset(output_dir: str) -> dict[str, str]:
    """
    Generates a deterministic set of test images in output_dir and returns
    a mapping of role -> absolute file path.
    """
    os.makedirs(output_dir, exist_ok=True)

    # 1. Base Image (240 x 240 with distinct colored shapes & gradients)
    base_img = Image.new("RGB", (240, 240), (20, 30, 45))
    draw = ImageDraw.Draw(base_img)
    draw.rectangle([30, 30, 110, 110], fill=(220, 50, 50), outline=(255, 255, 255))
    draw.ellipse([120, 40, 200, 120], fill=(50, 180, 220), outline=(255, 255, 255))
    draw.polygon([(40, 190), (120, 130), (200, 190)], fill=(220, 180, 40))
    draw.line([(0, 0), (240, 240)], fill=(255, 255, 255), width=2)

    base_path = os.path.join(output_dir, "base_image.jpg")
    base_img.save(base_path, format="JPEG", quality=95)

    # 2. Exact Copy (Identical bytes)
    exact_path = os.path.join(output_dir, "exact_copy.jpg")
    with open(base_path, "rb") as f_in, open(exact_path, "wb") as f_out:
        f_out.write(f_in.read())

    # 3. Resized Copy (180 x 180)
    resized_path = os.path.join(output_dir, "resized_copy.jpg")
    resized_img = base_img.resize((180, 180), Image.Resampling.BILINEAR)
    resized_img.save(resized_path, format="JPEG", quality=95)

    # 4. Recompressed Copy (Quality 45)
    recompressed_path = os.path.join(output_dir, "recompressed_copy.jpg")
    base_img.save(recompressed_path, format="JPEG", quality=45)

    # 5. Mildly Cropped Copy (5% crop from each edge, scaled back)
    w, h = base_img.size
    crop_box = (int(w * 0.05), int(h * 0.05), int(w * 0.95), int(h * 0.95))
    cropped_img = base_img.crop(crop_box).resize((240, 240), Image.Resampling.BICUBIC)
    cropped_path = os.path.join(output_dir, "cropped_copy.jpg")
    cropped_img.save(cropped_path, format="JPEG", quality=90)

    # 6. Visually Similar Pattern (Similar layout, shifted colors)
    similar_img = Image.new("RGB", (240, 240), (30, 45, 60))
    s_draw = ImageDraw.Draw(similar_img)
    s_draw.rectangle([35, 35, 115, 115], fill=(240, 70, 70))
    s_draw.ellipse([125, 45, 205, 125], fill=(70, 200, 240))
    s_draw.polygon([(45, 195), (125, 135), (205, 195)], fill=(240, 200, 60))
    similar_path = os.path.join(output_dir, "similar_pattern.jpg")
    similar_img.save(similar_path, format="JPEG", quality=90)

    # 7. Unrelated Image (Horizontal bars in bright greens & magenta)
    unrelated_img = Image.new("RGB", (240, 240), (255, 0, 128))
    u_draw = ImageDraw.Draw(unrelated_img)
    for y in range(0, 240, 20):
        u_draw.rectangle([0, y, 240, y + 10], fill=(0, 255, 100))
    unrelated_path = os.path.join(output_dir, "unrelated_image.jpg")
    unrelated_img.save(unrelated_path, format="JPEG", quality=90)

    # 8. Unindexed Query (Blue radial grid on black)
    unindexed_img = Image.new("RGB", (240, 240), (5, 5, 10))
    ui_draw = ImageDraw.Draw(unindexed_img)
    for r in range(10, 120, 15):
        ui_draw.ellipse([120 - r, 120 - r, 120 + r, 120 + r], outline=(0, 120, 255), width=2)
    unindexed_path = os.path.join(output_dir, "unindexed_query.jpg")
    unindexed_img.save(unindexed_path, format="JPEG", quality=90)

    return {
        "base": base_path,
        "exact": exact_path,
        "resized": resized_path,
        "recompressed": recompressed_path,
        "cropped": cropped_path,
        "similar": similar_path,
        "unrelated": unrelated_path,
        "unindexed": unindexed_path,
    }
