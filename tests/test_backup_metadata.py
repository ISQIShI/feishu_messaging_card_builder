import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")
UPDATE_SH = (PROJECT_ROOT / "update.sh").read_text(encoding="utf-8")
UNINSTALL_SH = (PROJECT_ROOT / "uninstall.sh").read_text(encoding="utf-8")
CHECK_SH = (PROJECT_ROOT / "check.sh").read_text(encoding="utf-8")


class BackupMetadataTests(unittest.TestCase):
    def test_install_records_original_run_metadata(self):
        self.assertIn("metadata.json", INSTALL_SH)
        self.assertIn('"original_run_backup"', INSTALL_SH)
        self.assertIn('写入元数据 "$BACKUP_DIR/run.py" "install"', INSTALL_SH)

    def test_update_preserves_original_run_backup_chain(self):
        self.assertIn("metadata.json", UPDATE_SH)
        self.assertIn("original_run_backup", UPDATE_SH)
        self.assertIn("解析原始备份", UPDATE_SH)
        self.assertIn('cp "$ORIGINAL_RUN_BACKUP" "$RUN_PY"', UPDATE_SH)
        self.assertNotIn('original_run.py', UPDATE_SH)

    def test_uninstall_prefers_original_run_backup_from_metadata(self):
        self.assertIn("metadata.json", UNINSTALL_SH)
        self.assertIn("original_run_backup", UNINSTALL_SH)
        self.assertIn("已从原始备份恢复 run.py", UNINSTALL_SH)

    def test_check_reports_original_backup_metadata(self):
        self.assertIn("metadata.json", CHECK_SH)
        self.assertIn("original_run_backup", CHECK_SH)


if __name__ == "__main__":
    unittest.main()
