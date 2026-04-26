import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_ENTRY = PROJECT_ROOT / "feishu_card_build" / "__main__.py"
LEGACY_ENTRY = PROJECT_ROOT / "feishu_card_build" / "feishu_card_build.py"
TMP_PAYLOAD = PROJECT_ROOT / "tests" / "tmp_payload_entry.json"


class PackageEntrypointTests(unittest.TestCase):
    def run_module(self):
        TMP_PAYLOAD.write_text(
            json.dumps(
                {
                    "chat_id": "oc_test",
                    "response": "## 标题\n\n正文",
                    "model": "gpt-test",
                    "response_time_seconds": 1,
                    "api_calls": 1,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return subprocess.run(
            [sys.executable, "-m", "feishu_card_build", "--input", str(TMP_PAYLOAD), "--dry-run"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
        )

    def test_package_has___main___entry(self):
        self.assertTrue(MAIN_ENTRY.exists(), "缺少 feishu_card_build/__main__.py")

    def test_python_m_feishu_card_build_works(self):
        proc = self.run_module()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["cards"])

    def test_legacy_script_entry_is_removed(self):
        self.assertFalse(LEGACY_ENTRY.exists(), "技术债未清理：仍存在 feishu_card_build/feishu_card_build.py")


if __name__ == "__main__":
    unittest.main()
