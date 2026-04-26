import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = PROJECT_ROOT / "run.py.patch"


class PatchInvocationTests(unittest.TestCase):
    def test_patch_uses_python_module_invocation(self):
        content = PATCH_PATH.read_text(encoding="utf-8")
        self.assertIn('"-m"', content)
        self.assertIn('"feishu_card_build"', content)

    def test_shell_scripts_apply_unified_diff_patch_from_hermes_home_with_p0(self):
        for name in ("install.sh", "update.sh", "check.sh"):
            content = (PROJECT_ROOT / name).read_text(encoding="utf-8")
            self.assertIn('cd "$HERMES_HOME"', content)
            self.assertIn('-p0', content)

    def test_patch_no_longer_targets_legacy_entry_script_path(self):
        content = PATCH_PATH.read_text(encoding="utf-8")
        self.assertNotIn('/ "feishu_card_build" / "feishu_card_build.py"', content)

    def test_patch_collects_last_reasoning_tools_and_builder_config_for_final_card(self):
        content = PATCH_PATH.read_text(encoding="utf-8")
        self.assertIn('"reasoning": str(agent_result.get("last_reasoning") or "").strip()', content)
        self.assertIn('"tools": _format_feishu_tool_panel(agent_result.get("messages"))', content)
        self.assertIn('_runtime_provider = ""', content)
        self.assertIn('_resolve_runtime_agent_kwargs() or {}', content)
        self.assertIn('"provider": str(agent_result.get("provider") or _runtime_provider or "").strip()', content)
        self.assertIn('"reasoning_effort": str(_agent_cfg.get("reasoning_effort") or "").strip().lower()', content)
        self.assertIn('_pre_turn_usage = {}', content)
        self.assertIn('agent_result["_feishu_turn_input_tokens"] = _usage_delta("input_tokens")', content)
        self.assertIn('"input_tokens": agent_result.get("_feishu_turn_input_tokens", 0) or 0', content)
        self.assertIn('"cache_read_tokens": agent_result.get("_feishu_turn_cache_read_tokens", 0) or 0', content)
        self.assertIn('"agent": _agent_cfg', content)
        self.assertIn('"tool_display_mode"', content)

    def test_patch_disables_tool_progress_and_interim_messages_in_feishu_card_mode(self):
        content = PATCH_PATH.read_text(encoding="utf-8")
        self.assertIn('tool_progress_enabled = False', content)
        self.assertIn('interim_assistant_messages_enabled = False', content)

    def test_patch_collects_only_assistant_tool_calls_without_tool_results(self):
        content = PATCH_PATH.read_text(encoding="utf-8")
        self.assertIn('msg.get("role") != "assistant"', content)
        self.assertIn('tool_calls = msg.get("tool_calls")', content)
        self.assertNotIn('↳ `', content)


if __name__ == "__main__":
    unittest.main()
