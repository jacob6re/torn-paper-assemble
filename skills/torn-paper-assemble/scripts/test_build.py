"""Check person/background complementarity, rejected masks, and scene regression."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw


class PartitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.frame = Image.new("RGB", (160, 240), "#598a72")
        ImageDraw.Draw(self.frame).rectangle((0, 120, 159, 239), fill="#d39569")
        self.frame.save(self.root / "frame.png")
        self.mask = Image.new("L", self.frame.size)
        draw = ImageDraw.Draw(self.mask)
        draw.ellipse((45, 25, 115, 95), fill=255)
        draw.rectangle((40, 90, 120, 239), fill=255)
        self.mask.save(self.root / "mask.png")
        self.config = {"mode": "person", "pieces": [
            {"from": [0, 1.1]},
            {"polygon": [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]], "from": [-1.1, 0]},
            {"polygon": [[0.5, 0], [1, 0], [1, 0.5], [0.5, 0.5]], "from": [1.1, 0]},
            {"polygon": [[0, 0.5], [0.5, 0.5], [1, 0.5], [1, 1], [0, 1]], "from": [0, 1.1]}]}

    def tearDown(self):
        self.temp.cleanup()

    def build(self, supplied=True):
        (self.root / "pieces.json").write_text(json.dumps(self.config))
        args = [sys.executable, str(Path(__file__).with_name("build.py")),
                "--input", str(self.root / "frame.png"), "--pieces", str(self.root / "pieces.json"),
                "--output", str(self.root / "project")]
        if supplied:
            args += ["--person-mask", str(self.root / "mask.png")]
        return subprocess.run(args, text=True, capture_output=True)

    def assert_reconstructs(self):
        output = self.root / "project/assets"
        coverage = Image.new("L", self.frame.size)
        restored = Image.new("RGB", self.frame.size)
        for i in range(4):
            with Image.open(output / f"piece-{i}.png") as piece:
                alpha = piece.getchannel("A")
                coverage = ImageChops.add(coverage, alpha.point(lambda x: 1 if x else 0))
                restored.paste(piece, mask=alpha)
                if self.config["mode"] == "person" and i:
                    self.assertIsNone(ImageChops.multiply(alpha, self.mask).getbbox())
        self.assertEqual(coverage.getextrema(), (1, 1))
        self.assertIsNone(ImageChops.difference(self.frame, restored).getbbox())

    def test_person_plus_three_backgrounds(self):
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        with Image.open(self.root / "project/assets/piece-0.png") as person:
            self.assertIsNone(ImageChops.difference(person.getchannel("A"), self.mask).getbbox())
        self.assert_reconstructs()

    def test_wrong_size_mask_rejected(self):
        Image.new("L", (10, 10)).save(self.root / "mask.png")
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("matching the processed frame", result.stderr)

    def test_empty_mask_rejected(self):
        Image.new("L", self.frame.size).save(self.root / "mask.png")
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("person mask", result.stderr)

    def test_scene_regression(self):
        self.config["mode"] = "scene"
        self.config["pieces"] = [
            {"polygon": [[x, y], [x+0.5, y], [x+0.5, y+0.5], [x, y+0.5]], "from": [0, 1.1]}
            for x, y in [(0, 0), (0.5, 0), (0, 0.5), (0.5, 0.5)]]
        result = self.build(supplied=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_reconstructs()

    def test_shared_edge_endpoint_rounding(self):
        self.frame = self.frame.resize((720, 960))
        self.frame.save(self.root / "frame.png")
        self.mask = self.mask.resize(self.frame.size, Image.Resampling.NEAREST)
        self.mask.save(self.root / "mask.png")
        self.config["pieces"][1:] = [
            {"polygon": [[0,0],[1,0],[1,0.32],[0.5,0.32],[0,0.32]], "from": [0,-1.1]},
            {"polygon": [[0,0.32],[0.5,0.32],[0.63,1],[0,1]], "from": [-1.1,0]},
            {"polygon": [[0.5,0.32],[1,0.32],[1,1],[0.63,1]], "from": [1.1,0]}]
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_reconstructs()


if __name__ == "__main__":
    unittest.main()
