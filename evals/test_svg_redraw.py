from contextlib import redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_svg_pair import named_objects, rgba_probe, validate_edit
from compare_ref import measure


SCENE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 4">
  <defs><g id="definition" data-element="definition"/></defs>
  <g id="panel" data-element="panel"><g id="front" data-element="front">
    <rect x="1" y="1" width="1" height="1" fill="#14a"/>
  </g></g>
</svg>"""


class SvgRedrawTests(unittest.TestCase):
    def test_foreground_union_counts_extra_and_missing_paint(self):
        with tempfile.TemporaryDirectory() as directory:
            ref, mine = (Path(directory) / f"{name}.png" for name in ("ref", "mine"))
            a = Image.new("RGBA", (6, 4))
            a.putpixel((0, 0), (0, 0, 0, 255))
            a.save(ref)
            b = a.copy()
            b.putpixel((0, 0), (0, 0, 0, 0))
            b.putpixel((1, 0), (0, 0, 0, 255))
            b.save(mine)
            report = measure(ref, mine, [("object", 0, 0, 2, 1), ("blank", 2, 0, 6, 4)])
            self.assertAlmostEqual(report["canvas"]["rgb_mae"], 21.25)
            self.assertEqual(report["regions"]["object"]["foreground_pixels"], 2)
            self.assertEqual(report["regions"]["object"]["foreground_rgb_mae"], 255)
            self.assertIsNone(report["regions"]["blank"]["foreground_rgb_mae"])
            self.assertIsNone(report["regions"]["blank"]["psnr_db"])
            with self.assertRaisesRegex(ValueError, "outside image"):
                measure(ref, mine, [("bad crop", 0, 0, 7, 4)])
            b.crop((0, 0, 3, 4)).save(mine)
            with self.assertRaisesRegex(ValueError, "identical pixel dimensions"):
                measure(ref, mine)

    def test_nested_hide_cannot_change_geometry_or_shared_definitions(self):
        root, hidden = ET.fromstring(SCENE), ET.fromstring(SCENE)
        front = named_objects(hidden)["front"]
        front.set("display", "none")
        validate_edit(root, hidden, ["front"], "display")
        front[0].set("fill", "red")
        with self.assertRaisesRegex(ValueError, "outside the declared"):
            validate_edit(root, hidden, ["front"], "display")
        with self.assertRaisesRegex(ValueError, "Unknown changed object"):
            validate_edit(root, hidden, ["definition"], "display")
        front[0].set("fill", "#14a")
        hidden[0][0].set("display", "none")
        with self.assertRaisesRegex(ValueError, "outside the declared"):
            validate_edit(root, hidden, ["front"], "display")

    def test_remove_existing_transform(self):
        original = ET.fromstring(SCENE.replace('<g id="front"', '<g transform="translate(1 0)" id="front"'))
        edited = ET.fromstring(SCENE)
        validate_edit(original, edited, ["front"], "transform")
        self.assertEqual(named_objects(original)["front"].get("transform"), "translate(1 0)")

    def test_rgba_diagnostics_keep_exact_probe_strict_by_default(self):
        root, edited = ET.fromstring(SCENE), ET.fromstring(SCENE)
        original, moved = named_objects(root)["panel"], named_objects(edited)["panel"]
        moved.set("transform", "translate(1 0)")
        frames = []
        for x, value in [(1, 100), (2, 103)]:
            img = Image.new("RGBA", (4, 4))
            img.putpixel((x, 1), (value, 0, 0, 128))
            with BytesIO() as data:
                img.save(data, format="PNG")
                frames.append(data.getvalue())
        with patch("cairosvg.svg2png", side_effect=frames):
            with self.assertRaisesRegex(ValueError, "Intrinsic RGBA changed"):
                rgba_probe(root, original, moved)
        with patch("cairosvg.svg2png", side_effect=frames), redirect_stdout(StringIO()) as out:
            rgba_probe(root, original, moved, report_only=True)
        self.assertIn("Premultiplied RGBA MAE", out.getvalue())
        self.assertIn("Exact RGBA equality not met", out.getvalue())


if __name__ == "__main__":
    unittest.main()
