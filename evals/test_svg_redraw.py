from contextlib import redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

import cairosvg
import numpy as np
from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from check_svg_pair import named_objects, rgba_probe, validate_edit
from compare_ref import measure
from fidelity_gate import PROFILES, compare, compare_structure
from spec_compile import resolve_endpoint
from svg_glazes import Glaze, Scale, fit_glazes
from svg_zoom_review import render_crop


SCENE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 4">
  <defs><g id="definition" data-element="definition"/></defs>
  <g id="panel" data-element="panel"><g id="front" data-element="front">
    <rect x="1" y="1" width="1" height="1" fill="#14a"/>
  </g></g>
</svg>"""


class SvgRedrawTests(unittest.TestCase):
    def test_structure_gate_catches_thin_line_drift_even_when_color_gate_passes(self):
        regions = {"axis": (27, 20, 72, 89)}
        frames = []
        for x in (45, 51):
            image = Image.new("RGB", (160, 100), "white")
            ImageDraw.Draw(image).line((x, 25, x, 82), fill="#303030")
            frames.append(np.asarray(image, dtype=np.float32))
        ref, shifted = frames
        self.assertEqual(compare(ref, shifted, PROFILES["edit"], regions)[0]["status"], "pass")
        self.assertEqual(compare_structure(ref, ref, regions)[0]["status"], "pass")
        report, overlay = compare_structure(ref, shifted, regions)
        self.assertEqual(report["status"], "fail")
        self.assertLess(report["regions"]["axis"]["recall"], 0.75)
        self.assertLess(report["regions"]["axis"]["precision"], 0.75)
        self.assertTrue(np.any(np.all(overlay == (214, 25, 71), axis=-1)))
        self.assertTrue(np.any(np.all(overlay == (0, 140, 210), axis=-1)))

    def test_spec_endpoint_shorthand_and_anchor_both_honor_offsets(self):
        elements = {"tip": {"x_mm": 20, "y_mm": 30, "width_mm": 8, "height_mm": 4}}
        self.assertEqual(resolve_endpoint("tip", elements, [-2, 3], "path.to"), (18, 33))
        self.assertEqual(resolve_endpoint({"element": "tip", "anchor": "left"},
                                          elements, [-2, 3], "path.to"), (14, 33))

    def test_review_requires_and_records_distinct_variants_zoom_and_visible_edits(self):
        import json

        scene = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 64">
          <defs><linearGradient id="paint"><stop stop-color="#23b"/><stop offset="1" stop-color="#7bf"/></linearGradient></defs>
          <g id="rear" data-element="rear"><rect x="3" y="24" width="90" height="4" fill="#970"/></g>
          <g id="front" data-element="front"><circle cx="38" cy="30" r="13" fill="url(#paint)"/></g>
        </svg>"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ref, edit, texture = (root / name for name in ("ref.png", "edit.svg", "texture.svg"))
            source = root / "draw.py"
            edit.write_text(scene, encoding="utf-8")
            texture.write_text(scene.replace('id="front" data-element="front"',
                                'id="front" data-element="front" data-role="intrinsic-RGBA-vector-texture"'),
                               encoding="utf-8")
            source.write_text(f"SCENE = {scene!r}", encoding="utf-8")
            cairosvg.svg2png(bytestring=scene.encode(), output_width=96, output_height=64, write_to=str(ref))
            out = root / "out"
            command = [sys.executable, "-X", "utf8", str(SCRIPTS / "review_redraw.py"),
                       "--reference", str(ref), "--edit", str(edit), "--texture", str(texture),
                       "--source", str(source), "--region", "circle", "18", "12", "62", "51",
                       "--structure", "circle", "--move", "front", "25", "8", "--outdir", str(out)]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((out / "review.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")
            for kind in ("edit", "texture"):
                self.assertTrue((out / report["checks"][f"{kind}_probe"]["image"]).exists())
            self.assertTrue((out / "zoom" / "circle.zoom.png").exists())
            command[command.index("--texture") + 1] = str(edit)
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=45)
            self.assertEqual(result.returncode, 2)
            self.assertIn("distinct SVG files", result.stderr)

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

    def test_zoom_keeps_original_percentage_geometry_and_viewbox_offset(self):
        contents = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="10 20 100 60" width="200" height="120">'
            '<g id="test" data-element="test"><rect x="50%" y="6" width="25%" height="80%" fill="#151517"/>'
            '<circle cx="95" cy="13" r="10" fill="#e96"/></g></svg>'
        )
        root = ET.fromstring(contents)
        saved = ET.tostring(root)
        region = (60, 16, 184, 101)
        zoom = render_crop(root, (200, 120), region, 4)
        raw = cairosvg.svg2png(bytestring=contents.encode(), output_width=800, output_height=480, background_color="white")
        with Image.open(BytesIO(raw)) as full:
            expected = full.convert("RGB").crop(tuple(4 * coordinate for coordinate in region))
        np.testing.assert_array_equal(np.asarray(zoom), np.asarray(expected))
        self.assertEqual(ET.tostring(root), saved)

    def test_calibrated_glazes_ignore_occluded_pixels(self):
        base = np.full((36, 48, 3), 80, dtype=float)
        target = base.copy()
        target[4:24, 6:23] = (180, 100, 55)
        visible = np.ones(base.shape[:2], dtype=float)
        visible[14:28, 26:38] = 0
        contaminated = target.copy()
        contaminated[visible == 0] = (15, 45, 241)
        schedule = [Scale(7, 10, 2, .8), Scale(3, 5, 1, 1)]
        expected = fit_glazes(target, base, visible, schedule)
        self.assertGreater(len(expected), 1)
        self.assertEqual(fit_glazes(contaminated, base, visible, schedule), expected)

    def test_clipped_glaze_preserves_gradient_coordinates_and_exterior(self):
        base = Glaze(20, 15, 12, (255, 120, 53))
        outline = ((8, 5), (22, 5), (22, 24), (8, 24))
        plain, _ = base.svg("glaze")
        definition, shape = base.svg("glaze", convex_outline=outline)
        self.assertEqual(plain, definition)
        payload = ('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30">'
                   f'<defs>{definition}</defs>{shape}</svg>')
        raw = cairosvg.svg2png(bytestring=payload.encode())
        with Image.open(BytesIO(raw)) as image:
            self.assertGreater(image.getpixel((20, 15))[3], 100)
            self.assertEqual(image.getpixel((24, 15))[3], 0)

    def test_generated_compare_ref_shim_loads_sibling_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            python = [sys.executable, "-X", "utf8"]
            subprocess.run(python + [str(SCRIPTS / "init_workspace.py"), "--dir", directory],
                           check=True, capture_output=True, cwd=workspace, timeout=30)
            shim = workspace / "tools" / "compare_ref.py"
            result = subprocess.run(python + [str(shim), "--help"], check=True, capture_output=True,
                                    encoding="utf-8", cwd=workspace, timeout=30)
            self.assertIn("--metrics", result.stdout)
            for name in ("fidelity_gate", "svg_zoom_review", "review_redraw"):
                executable = workspace / "tools" / f"{name}.py"
                subprocess.run(python + [str(executable), "--help"], check=True, capture_output=True,
                               encoding="utf-8", cwd=workspace, timeout=30)


if __name__ == "__main__":
    unittest.main()
