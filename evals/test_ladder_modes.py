import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ladder_gate import do_record, precheck, load_ledger
from ir_scope_gate import check as check_scope, ir_view

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class LadderModes(unittest.TestCase):
    def test_guided_baseline_rejects_shape_and_color_on_both_rungs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hand = root / "sketches_in" / "sketch.png"
            hand.parent.mkdir()
            hand.touch()
            a_brief, brief = root / "A.md", root / "brief.md"
            neutral = "画高能核物理中的三维喷注淬火期刊示意图，展示背对背喷注。"
            physics_terms = "画三维示意图，展示圆偏振探针、红外辐射、蓝移和色荷。"
            prescribed = [
                ("画三维喷注淬火示意图，暖色椭球 QGP 配蓝色喷注。", ("暖色", "椭球", "蓝色")),
                ("画一张近圆的橙红QGP图。", ("近圆", "橙红")),
                ("画三维喷注淬火示意图，QGP 不是椭圆。", ("椭圆",)),
                ("Draw an oblate QGP with cobalt blue jets.", ("oblate", "blue")),
                ("画三维喷注淬火示意图，介质用 #F80。", ("#F80",)),
            ]

            def pre(tier, text, content):
                brief.write_text(text, encoding="utf-8")
                return precheck(root, brief, root / tier, [], "sketch", content, tier=tier)[1]

            for value in (neutral, physics_terms):
                self.assertEqual(pre("A", value, [hand]), [])
            for value, tokens in prescribed:
                with self.subTest(tier="A", text=value):
                    errors = pre("A", value, [hand])
                    self.assertTrue(any(e.startswith("L2") and all(t in e for t in tokens) for e in errors), errors)
                    self.assertEqual(pre("A", value, []), [])  # existing no-sketch route

            a_brief.write_text(neutral, encoding="utf-8")
            do_record(root, a_brief, root / "A", [], content_refs=[hand])
            self.assertEqual(pre("B", neutral, []), [])
            for value, tokens in prescribed:
                with self.subTest(tier="B", text=value):
                    # Even if A was recorded before this rule existed, B must not pass the old styling.
                    a_brief.write_text(value, encoding="utf-8")
                    errors = pre("B", value, [])
                    self.assertTrue(any(e.startswith("L2") and all(t in e for t in tokens) for e in errors), errors)

    def test_author_sketch_ladder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hand = root / "sketches_in" / "author.png"
            hand.parent.mkdir()
            hand.touch()
            style = root / "_T3精选" / "style.png"
            brief = root / "brief.md"
            images = {tier: root / tier / "sketch.png" for tier in "ABCDE"}
            for path in images.values():
                path.parent.mkdir()
                path.touch()
            one = "画三维科研示意图。"
            base = one + "单面板；图上只许出现这些标签：beam。不要标题，不要图例。\n【参考图自带、本图不要】网格。"
            merge = base + "\n逐元素比较 A、B、C 三档，以 C 档为底稿，选择优秀元素替换 C 档中对应处，其余原样保留。"
            fix = base + "\n════ 上一轮画错的地方（这一轮必须改对）════\n严格在上一张图上改，其余原样保留，不许重画。\n[HP1] 核形变方向错了，改成沿束流压扁的椭球，不要修改材质。"

            def check(tier, body, refs, content, stage="sketch", code=None, claim=None):
                brief.write_text(body, encoding="utf-8")
                rung, errors, _, _ = precheck(root, brief, root / tier, refs, stage, content, tier=claim)
                self.assertEqual(rung, tier if stage == "sketch" else "E")
                if code:
                    self.assertTrue(any(e.startswith(code) for e in errors), errors)
                else:
                    self.assertEqual(errors, [])

            def register(tier, body, refs, content):
                check(tier, body, refs, content, claim=tier)
                # Keep the historical brief immutable, as in a real run.
                saved = root / tier / "brief.md"
                saved.write_text(body, encoding="utf-8")
                do_record(root, saved, root / tier, refs, content_refs=content)

            register("A", one, [], [hand])
            self.assertEqual(load_ledger(root)["mode"], "with-sketch")
            check("B", one, [style], [], code="L2")
            check("B", one, [], [hand], code="L9")
            check("B", "另一句话。", [], [], code="L2")
            register("B", one, [], [])
            check("C", base, [style], [hand], code="L9")
            check("C", base, [style], [], code="L1", claim="D")
            register("C", base, [style], [])
            sources = [images[tier] for tier in "ABC"]
            for omitted in sources:
                check("D", merge, [style], [p for p in sources if p != omitted], code="L9")
            check("D", merge, [style], sources + [hand], code="L9")
            check("D", merge.replace("A、B、C", "A、C"), [style], sources, code="L12")
            register("D", merge, [style], sources)
            render = fix + "\n在上一张图的基础上改，不要换掉原来画对的元素。"
            check("render", render, [style], [images["D"]], "render", code="L6")
            check("E", fix, [style], [images["C"]], code="L9")
            register("E", fix, [style], [images["D"]])
            check("render", render, [style], [images["D"]], "render", code="L13")
            check("render", render, [style], [images["E"]], "render")

    def test_existing_ledger_keeps_four_rungs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ladder.json").write_text('{"version":1,"rungs":[{"rung":"A"}]}', encoding="utf-8")
            brief = root / "brief.md"
            brief.write_text("画三维科研示意图。单面板；图上只许出现这些标签：beam；不要图例、标题及说明文字。", encoding="utf-8")
            rung, errors, _, _ = precheck(root, brief, root / "B", ["style.png"], "sketch", [])
            self.assertEqual((rung, errors), ("B", []))

    def test_style_rung_can_list_ir_labels_but_not_copy_style(self):
        label = "Medium-induced radiation"
        convention = "着色使用连续径向渐变和明暗分层"
        view = ir_view({"style": {"conventions": [f"标签：{label}", convention]}})
        whitelist = f"图上只许出现这些标签：QGP, {label}。"
        self.assertEqual(check_scope("C", whitelist, view, "with-sketch")[0], [])
        errors, _, _ = check_scope("C", whitelist + "\n" + convention, view, "with-sketch")
        self.assertIn("S1_IR_CONVENTIONS_IN_BRIEF", [kind for kind, _ in errors])

    def test_run_dry_run_does_not_advance_and_checks_actual_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hand = root / "sketches_in" / "sketch.png"
            hand.parent.mkdir()
            hand.touch()
            brief = root / "brief.md"
            brief.write_text("画三维科研示意图。", encoding="utf-8")
            cmd = [sys.executable, str(SCRIPTS / "ref_guard.py"), "--run",
                   "--stage", "sketch", "--tier", "A", "--ladder-gen-dir", str(root),
                   "--content-ref", str(hand), "--brief", str(brief), "--",
                   f"--outdir={root / 'A'}", "--allow-no-ref", "--dry-run"]
            result = subprocess.run(cmd, capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((root / "ladder.json").exists())
            result = subprocess.run(cmd + [f"--content-ref={root / 'other.png'}"],
                                    capture_output=True, encoding="utf-8")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ARG_MISMATCH", result.stdout)


if __name__ == "__main__":
    unittest.main()
