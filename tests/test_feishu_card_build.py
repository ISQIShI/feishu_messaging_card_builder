import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from feishu_card_build.builder import CardBuilder, cards_to_json
from feishu_card_build.config import resolve_builder_kwargs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TMP_PAYLOAD = PROJECT_ROOT / "tests" / "tmp_payload.json"


class FeishuCardBuildTests(unittest.TestCase):
    def setUp(self):
        self._home_tmp = tempfile.TemporaryDirectory()
        self.test_home = Path(self._home_tmp.name)
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.test_home)

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        self._home_tmp.cleanup()

    def run_builder(self, payload: dict):
        TMP_PAYLOAD.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-m", "feishu_card_build", "--input", str(TMP_PAYLOAD), "--dry-run"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT), "HOME": str(self.test_home)},
        )

    def test_builds_schema_2_cards_with_table_and_lark_md_footer(self):
        proc = self.run_builder(
            {
                "chat_id": "oc_test",
                "response": """[[HERMES_STATUS:completed]]
## 巡检结论

| 指标 | 值 |
| --- | --- |
| CPU | 45% |
| 内存 | 72% |

系统总体正常。
""",
                "provider": "anthropic",
                "model": "gpt-test",
                "reasoning_effort": "medium",
                "response_time_seconds": 2.5,
                "api_calls": 3,
                "last_prompt_tokens": 1200,
                "input_tokens": 1800,
                "output_tokens": 320,
                "cache_read_tokens": 640,
                "config_context_length": 8000,
            }
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["cards"])

        card = data["cards"][0]
        self.assertEqual(card["schema"], "2.0")
        self.assertEqual(card.get("config", {}).get("width_mode"), "fill")
        self.assertNotIn("wide_screen_mode", card.get("config", {}))
        self.assertNotIn("header", card)

        elements = card["body"]["elements"]
        self.assertTrue(any(element["tag"] == "table" for element in elements))
        footer_blocks = [element["text"]["content"] for element in elements if element["tag"] == "div" and element["text"]["tag"] == "lark_md"]
        self.assertTrue(footer_blocks)
        footer = footer_blocks[-1]
        self.assertIn("anthropic · gpt-test (medium)", footer)
        self.assertIn("调用API 3 次", footer)
        self.assertIn("\n", footer)
        self.assertIn("输入 1.8k", footer)
        self.assertIn("输出 320", footer)
        self.assertIn("缓存读 640", footer)
        self.assertIn("上下文 1.2k/8.0k", footer)

    def test_strips_gateway_reasoning_prefix_from_body_when_payload_reasoning_exists(self):
        proc = self.run_builder(
            {
                "chat_id": "oc_test",
                "response": "💭 **Reasoning:**\n```\n这是网关插入的 reasoning\n```\n\n## 结果\n\n主体内容。",
                "reasoning": "来自 payload 的思考过程",
                "model": "gpt-test",
                "response_time_seconds": 1,
                "api_calls": 1,
            }
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        card = json.loads(proc.stdout)["cards"][0]
        elements = card["body"]["elements"]
        markdown_blocks = [element["content"] for element in elements if element["tag"] == "markdown"]
        self.assertTrue(all("💭 **Reasoning:**" not in block for block in markdown_blocks))
        self.assertTrue(all("这是网关插入的 reasoning" not in block for block in markdown_blocks))
        panels = [element for element in elements if element["tag"] == "collapsible_panel"]
        self.assertTrue(any(panel["header"]["title"]["content"] == "💭 思考过程" and "来自 payload 的思考过程" in "\n".join(el["content"] for el in panel["elements"] if el["tag"] == "markdown") for panel in panels))
        self.assertTrue(any(element["tag"] == "markdown" and "主体内容。" in element["content"] for element in elements))

    def test_extracts_reasoning_tools_and_removes_media_directives(self):
        proc = self.run_builder(
            {
                "chat_id": "oc_test",
                "response": """MEDIA:/tmp/demo.png
[[HERMES_STATUS:completed]]
## 结果

主体内容。

[[HERMES_REASONING]]
这里是思考过程
[[/HERMES_REASONING]]

[[HERMES_TOOLS]]
terminal(\"date\")
[[/HERMES_TOOLS]]

[[HERMES_FOOTER]]
自定义 Footer
[[/HERMES_FOOTER]]
""",
                "model": "gpt-test",
                "response_time_seconds": 1,
                "api_calls": 1,
            }
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        card = json.loads(proc.stdout)["cards"][0]
        elements = card["body"]["elements"]

        markdown_blocks = [element["content"] for element in elements if element["tag"] == "markdown"]
        self.assertTrue(all("MEDIA:" not in block for block in markdown_blocks))
        self.assertTrue(all("HERMES_REASONING" not in block for block in markdown_blocks))
        self.assertTrue(all("HERMES_TOOLS" not in block for block in markdown_blocks))

        panels = [element for element in elements if element["tag"] == "collapsible_panel"]
        panel_titles = [panel["header"]["title"]["content"] for panel in panels]
        self.assertEqual(panel_titles, ["🛠️ 工具调用", "💭 思考过程"])
        self.assertEqual(elements[0]["header"]["title"]["content"], "🛠️ 工具调用")
        self.assertEqual(elements[1]["header"]["title"]["content"], "💭 思考过程")
        self.assertTrue(all(panel["header"]["icon"]["token"] == "down-small-outlined" for panel in panels))
        tool_panel = next(panel for panel in panels if panel["header"]["title"]["content"] == "🛠️ 工具调用")
        reasoning_panel = next(panel for panel in panels if panel["header"]["title"]["content"] == "💭 思考过程")
        tool_panel_content = "\n".join(element["content"] for element in tool_panel["elements"] if element["tag"] == "markdown")
        reasoning_panel_content = "\n".join(element["content"] for element in reasoning_panel["elements"] if element["tag"] == "markdown")
        self.assertIn("terminal(\"date\")", tool_panel_content)
        self.assertIn("这里是思考过程", reasoning_panel_content)
        self.assertNotIn("片段 1", reasoning_panel_content)
        self.assertNotIn("---", reasoning_panel_content)
        markdown_blocks = [element["content"] for element in elements[2:] if element["tag"] == "markdown"]
        self.assertTrue(markdown_blocks)
        self.assertTrue(any("主体内容。" in block for block in markdown_blocks))
        self.assertTrue(any(element["tag"] == "div" and element["text"]["tag"] == "lark_md" and "自定义 Footer" in element["text"]["content"] for element in elements))

    def test_tool_panel_compacts_many_calls_to_avoid_card_length_limit(self):
        long_tools = "\n\n".join(
            f"- `todo`\n```json\n{{\"id\": {i}, \"content\": \"任务{i}\", \"status\": \"pending\", \"extra\": \"{'x'*40}\"}}\n```"
            for i in range(40)
        )
        proc = self.run_builder(
            {
                "chat_id": "oc_test",
                "response": "## 最终回答\n\n主体内容。",
                "tools": long_tools,
                "model": "gpt-test",
                "response_time_seconds": 1,
                "api_calls": 1,
            }
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        card = json.loads(proc.stdout)["cards"][0]
        panels = [element for element in card["body"]["elements"] if element["tag"] == "collapsible_panel"]
        tool_panel = next(panel for panel in panels if panel["header"]["title"]["content"] == "🛠️ 工具调用")
        combined = "\n".join(element["content"] for element in tool_panel["elements"] if element["tag"] == "markdown")
        self.assertIn("**`todo`**", combined)
        self.assertIn('"id": 0', combined)
        self.assertIn('"status": "pending"', combined)
        self.assertGreater(len(tool_panel["elements"]), 1)
        self.assertNotIn("调用分组", combined)

    def test_reasoning_prefers_last_reasoning_when_available(self):
        proc = self.run_builder(
            {
                "chat_id": "oc_test",
                "response": "## 最终回答\n\n主体内容。",
                "reasoning": "只有 payload 的摘要",
                "messages": [
                    {"role": "assistant", "reasoning": "第一段完整推理"},
                    {"role": "assistant", "reasoning": "第二段完整推理"},
                ],
                "last_reasoning": "最后一段",
                "model": "gpt-test",
                "response_time_seconds": 1,
                "api_calls": 1,
            }
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        card = json.loads(proc.stdout)["cards"][0]
        panels = [element for element in card["body"]["elements"] if element["tag"] == "collapsible_panel"]
        reasoning_panel = next(panel for panel in panels if panel["header"]["title"]["content"] == "💭 思考过程")
        combined = "\n".join(element["content"] for element in reasoning_panel["elements"] if element["tag"] == "markdown")
        self.assertIn("最后一段", combined)
        self.assertNotIn("第一段完整推理", combined)
        self.assertNotIn("第二段完整推理", combined)
        self.assertNotIn("只有 payload 的摘要", combined)

    def test_payload_reasoning_and_tools_also_render_as_collapsible_panels(self):
        proc = self.run_builder(
            {
                "chat_id": "oc_test",
                "response": "## 最终回答\n\n主体内容。",
                "reasoning": "从 payload 注入的思考过程",
                "tools": "- `terminal`\n```json\n{\"command\": \"date\"}\n```",
                "model": "gpt-test",
                "response_time_seconds": 1,
                "api_calls": 1,
            }
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        card = json.loads(proc.stdout)["cards"][0]
        elements = card["body"]["elements"]
        panels = [element for element in elements if element["tag"] == "collapsible_panel"]
        self.assertEqual(len(panels), 2)
        title_to_panel = {panel["header"]["title"]["content"]: panel for panel in panels}
        self.assertEqual(list(title_to_panel), ["🛠️ 工具调用", "💭 思考过程"])
        tool_panel_content = "\n".join(element["content"] for element in title_to_panel["🛠️ 工具调用"]["elements"] if element["tag"] == "markdown")
        reasoning_panel_content = "\n".join(element["content"] for element in title_to_panel["💭 思考过程"]["elements"] if element["tag"] == "markdown")
        self.assertIn("**`terminal`**", tool_panel_content)
        self.assertIn("{" + '"command": "date"' + "}", tool_panel_content)
        self.assertIn("从 payload 注入的思考过程", reasoning_panel_content)
        markdown_blocks = [element["content"] for element in elements[2:] if element["tag"] == "markdown"]
        self.assertTrue(markdown_blocks)
        self.assertTrue(any("主体内容。" in block for block in markdown_blocks))

    def test_can_disable_tool_panel_and_use_native_tool_sending(self):
        proc = self.run_builder(
            {
                "chat_id": "oc_test",
                "response": "## 最终回答\n\n主体内容。",
                "tools": "- `terminal`\n```json\n{\"command\": \"date\"}\n```",
                "reasoning": "保留 reasoning",
                "builder_config": {
                    "tool_display_mode": "native"
                },
                "model": "gpt-test",
                "response_time_seconds": 1,
                "api_calls": 1,
            }
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        card = json.loads(proc.stdout)["cards"][0]
        panels = [element for element in card["body"]["elements"] if element["tag"] == "collapsible_panel"]
        self.assertEqual([panel["header"]["title"]["content"] for panel in panels], ["💭 思考过程"])
        self.assertFalse(any("terminal" in "\n".join(el.get("content", "") for el in panel["elements"] if el["tag"] == "markdown") for panel in panels))
        self.assertTrue(any(element["tag"] == "markdown" and "主体内容。" in element["content"] for element in card["body"]["elements"]))

    def test_tool_scope_is_only_current_reply_payload(self):
        proc = self.run_builder(
            {
                "chat_id": "oc_test",
                "response": "## 最终回答\n\n主体内容。",
                "tools": "- `terminal`\n```json\n{\"command\": \"date\"}\n```",
                "messages": [
                    {"role": "assistant", "tool_calls": [{"function": {"name": "browser_click", "arguments": '{\"ref\":\"@e1\"}'}}]},
                ],
                "model": "gpt-test",
                "response_time_seconds": 1,
                "api_calls": 1,
            }
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        card = json.loads(proc.stdout)["cards"][0]
        panels = [element for element in card["body"]["elements"] if element["tag"] == "collapsible_panel"]
        tool_panel = next(panel for panel in panels if panel["header"]["title"]["content"] == "🛠️ 工具调用")
        combined = "\n".join(element["content"] for element in tool_panel["elements"] if element["tag"] == "markdown")
        self.assertIn("terminal", combined)
        self.assertNotIn("browser_click", combined)

    def test_tool_panel_has_structured_sections_and_preserves_long_tool_call_list(self):
        long_tools = "\n\n".join(
            f"- `todo`\n```json\n{{\"id\": {i}, \"content\": \"任务{i}\", \"status\": \"pending\"}}\n```"
            for i in range(30)
        )
        proc = self.run_builder(
            {
                "chat_id": "oc_test",
                "response": "## 最终回答\n\n主体内容。",
                "tools": long_tools,
                "model": "gpt-test",
                "response_time_seconds": 1,
                "api_calls": 1,
            }
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        card = json.loads(proc.stdout)["cards"][0]
        panels = [element for element in card["body"]["elements"] if element["tag"] == "collapsible_panel"]
        tool_panel = next(panel for panel in panels if panel["header"]["title"]["content"] == "🛠️ 工具调用")
        combined = "\n".join(element["content"] for element in tool_panel["elements"] if element["tag"] == "markdown")
        self.assertIn("**`todo`**", combined)
        self.assertIn('"id": 0', combined)
        self.assertIn('"status": "pending"', combined)
        self.assertIn("---", combined)
        self.assertNotIn("调用分组", combined)

    def test_reasoning_panel_has_structured_sections_and_uses_last_reasoning_only(self):
        proc = self.run_builder(
            {
                "chat_id": "oc_test",
                "response": "## 最终回答\n\n主体内容。",
                "reasoning": "旧的 payload reasoning",
                "last_reasoning": "第一段推理\n\n第二段推理\n\n第三段推理",
                "model": "gpt-test",
                "response_time_seconds": 1,
                "api_calls": 1,
            }
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        card = json.loads(proc.stdout)["cards"][0]
        panels = [element for element in card["body"]["elements"] if element["tag"] == "collapsible_panel"]
        reasoning_panel = next(panel for panel in panels if panel["header"]["title"]["content"] == "💭 思考过程")
        combined = "\n".join(element["content"] for element in reasoning_panel["elements"] if element["tag"] == "markdown")
        self.assertIn("第一段推理", combined)
        self.assertIn("第二段推理", combined)
        self.assertIn("第三段推理", combined)
        self.assertNotIn("---", combined)
        self.assertNotIn("片段 1", combined)
        self.assertNotIn("旧的 payload reasoning", combined)

    def test_truncate_mode_drops_panels_when_card_would_be_too_large(self):
        builder = CardBuilder(
            body_chunk_limit=5200,
            reasoning_max_length=3500,
            tools_max_length=3500,
            max_card_text_length=900,
            overflow_mode="truncate",
        )
        payload = {
            "chat_id": "oc_test",
            "response": "## 最终回答\n\n" + ("主体内容" * 1400),
            "tools": "\n\n".join(
                f"- `todo`\n```json\n{{\"id\": {i}, \"content\": \"任务{i}\", \"status\": \"pending\", \"extra\": \"{'x'*120}\"}}\n```"
                for i in range(180)
            ),
            "reasoning": ("推理片段\n\n" * 900),
            "model": "gpt-test",
            "response_time_seconds": 1,
            "api_calls": 1,
        }

        cards = builder.build_cards(payload)
        self.assertGreaterEqual(len(cards), 1)
        first_elements = cards[0]["body"]["elements"]
        self.assertFalse(any(element["tag"] == "collapsible_panel" for element in first_elements))
        all_markdown = [
            element["content"]
            for card in cards
            for element in card["body"]["elements"]
            if element["tag"] == "markdown"
        ]
        self.assertTrue(any("主体内容" in content for content in all_markdown))
        footer_card = cards[-1]
        self.assertTrue(any(element["tag"] == "div" and element["text"]["tag"] == "lark_md" for element in footer_card["body"]["elements"]))
        self.assertTrue(all(builder._card_text_length(card) <= 1400 for card in cards))

    def test_length_guard_keeps_panels_for_normal_payloads(self):
        builder = CardBuilder()
        payload = {
            "chat_id": "oc_test",
            "response": "## 最终回答\n\n主体内容。",
            "tools": "- `terminal`\n```json\n{\"command\": \"date\"}\n```",
            "reasoning": "一步\n\n二步",
            "model": "gpt-test",
            "response_time_seconds": 1,
            "api_calls": 1,
        }

        cards = builder.build_cards(payload)
        first_elements = cards[0]["body"]["elements"]
        self.assertTrue(any(element["tag"] == "collapsible_panel" for element in first_elements))

    def test_split_cards_mode_preserves_panels_by_sending_more_cards(self):
        builder = CardBuilder(
            body_chunk_limit=2200,
            reasoning_max_length=3500,
            tools_max_length=3500,
            max_card_text_length=900,
            overflow_mode="split_cards",
        )
        payload = {
            "chat_id": "oc_test",
            "response": "## 最终回答\n\n" + ("主体内容" * 900),
            "tools": "\n\n".join(
                f"- `todo`\n```json\n{{\"id\": {i}, \"content\": \"任务{i}\", \"status\": \"pending\"}}\n```"
                for i in range(90)
            ),
            "reasoning": ("推理片段\n\n" * 220),
            "model": "gpt-test",
            "response_time_seconds": 1,
            "api_calls": 1,
        }

        cards = builder.build_cards(payload)
        self.assertGreater(len(cards), 3)
        panel_cards = [card for card in cards if any(element["tag"] == "collapsible_panel" for element in card["body"]["elements"])]
        self.assertGreaterEqual(len(panel_cards), 2)
        self.assertTrue(any(any(element["tag"] == "collapsible_panel" and element["header"]["title"]["content"] == "🛠️ 工具调用" for element in card["body"]["elements"]) for card in panel_cards))
        self.assertTrue(any(any(element["tag"] == "collapsible_panel" and element["header"]["title"]["content"] == "💭 思考过程" for element in card["body"]["elements"]) for card in panel_cards))
        self.assertTrue(any(any(element["tag"] == "markdown" and "主体内容" in element["content"] for element in card["body"]["elements"] if element["tag"] == "markdown") for card in cards))
        self.assertTrue(all(builder._card_text_length(card) <= 4500 for card in panel_cards))
        non_panel_cards = [card for card in cards if not any(element["tag"] == "collapsible_panel" for element in card["body"]["elements"])]
        self.assertTrue(all(builder._card_text_length(card) <= 1400 for card in non_panel_cards))

    def test_truncate_mode_spills_panels_to_separate_cards_before_dropping_them(self):
        builder = CardBuilder(
            body_chunk_limit=2200,
            reasoning_max_length=3500,
            tools_max_length=3500,
            max_card_text_length=1400,
            overflow_mode="truncate",
        )
        payload = {
            "chat_id": "oc_test",
            "response": "## 最终回答\n\n" + ("主体内容" * 900),
            "tools": "\n\n".join(
                f"- `todo`\n```json\n{{\"id\": {i}, \"content\": \"任务{i}\", \"status\": \"pending\"}}\n```"
                for i in range(30)
            ),
            "reasoning": ("推理片段\n\n" * 90),
            "model": "gpt-test",
            "response_time_seconds": 1,
            "api_calls": 1,
        }

        cards = builder.build_cards(payload)
        self.assertGreater(len(cards), 1)
        panel_cards = [card for card in cards if any(element["tag"] == "collapsible_panel" for element in card["body"]["elements"])]
        self.assertTrue(panel_cards)
        panel_titles = [
            element["header"]["title"]["content"]
            for card in panel_cards
            for element in card["body"]["elements"]
            if element["tag"] == "collapsible_panel"
        ]
        self.assertIn("🛠️ 工具调用", panel_titles)
        self.assertIn("💭 思考过程", panel_titles)
        self.assertTrue(any(any(element["tag"] == "markdown" and "主体内容" in element["content"] for element in card["body"]["elements"] if element["tag"] == "markdown") for card in cards))

    def test_cli_builder_reads_length_protection_from_payload_override(self):
        proc = self.run_builder(
            {
                "chat_id": "oc_test",
                "response": "## 最终回答\n\n" + ("主体内容" * 900),
                "tools": "\n\n".join(
                    f"- `todo`\n```json\n{{\"id\": {i}, \"content\": \"任务{i}\", \"status\": \"pending\"}}\n```"
                    for i in range(60)
                ),
                "reasoning": ("推理片段\n\n" * 160),
                "builder_config": {
                    "length_protection": {
                        "max_card_text_length": 900,
                        "overflow_mode": "split_cards",
                    }
                },
                "model": "gpt-test",
                "response_time_seconds": 1,
                "api_calls": 1,
            }
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        cards = json.loads(proc.stdout)["cards"]
        self.assertGreater(len(cards), 2)
        self.assertTrue(any(any(element["tag"] == "collapsible_panel" for element in card["body"]["elements"]) for card in cards))

    def test_resolve_builder_kwargs_uses_new_default_length_protection(self):
        kwargs = resolve_builder_kwargs({"chat_id": "oc_test"})
        self.assertEqual(kwargs["max_card_text_length"], 6000)
        self.assertEqual(kwargs["overflow_mode"], "truncate")
        self.assertEqual(kwargs["body_chunk_limit"], 3200)

    def test_splits_long_content_into_multiple_cards(self):
        long_paragraph = "这是用于分片测试的内容。" * 600
        proc = self.run_builder(
            {
                "chat_id": "oc_test",
                "response": f"## 长文档\n\n{long_paragraph}",
                "model": "gpt-test",
                "response_time_seconds": 3,
                "api_calls": 2,
            }
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        cards = json.loads(proc.stdout)["cards"]
        self.assertGreaterEqual(len(cards), 2)
        self.assertFalse(any("header" in card for card in cards))

    def test_footer_no_longer_uses_note_or_header(self):
        proc = self.run_builder(
            {
                "chat_id": "oc_test",
                "response": "## Footer 检查\n\n正文",
                "model": "gpt-test",
                "response_time_seconds": 1,
                "api_calls": 1,
                "last_prompt_tokens": 1500,
                "config_context_length": 8000,
            }
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        card = json.loads(proc.stdout)["cards"][0]
        elements = card["body"]["elements"]
        self.assertNotIn("header", card)
        self.assertFalse(any(element["tag"] == "note" for element in elements))
        self.assertTrue(any(element["tag"] == "div" and element["text"]["tag"] == "lark_md" for element in elements))

    def test_footer_reads_reasoning_effort_only_from_payload_field(self):
        proc = self.run_builder(
            {
                "chat_id": "oc_test",
                "response": "## Footer 检查\n\n正文",
                "provider": "openrouter",
                "model": "gpt-test",
                "reasoning_effort": "HIGH",
                "agent": {"reasoning_effort": "low"},
                "response_time_seconds": 1,
                "api_calls": 1,
            }
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        card = json.loads(proc.stdout)["cards"][0]
        elements = card["body"]["elements"]
        self.assertTrue(any(element["tag"] == "div" and element["text"]["tag"] == "lark_md" and "openrouter · gpt-test (high)" in element["text"]["content"] for element in elements))
        self.assertFalse(any(element["tag"] == "div" and element["text"]["tag"] == "lark_md" and "gpt-test (low)" in element["text"]["content"] for element in elements))

    def test_footer_prefers_feishu_turn_token_values_when_present(self):
        proc = self.run_builder(
            {
                "chat_id": "oc_test",
                "response": "## Footer 检查\n\n正文",
                "provider": "anthropic",
                "model": "gpt-test",
                "response_time_seconds": 1,
                "api_calls": 1,
                "input_tokens": 999999,
                "output_tokens": 888888,
                "cache_read_tokens": 777777,
                "_feishu_turn_input_tokens": 1234,
                "_feishu_turn_output_tokens": 56,
                "_feishu_turn_cache_read_tokens": 789,
                "last_prompt_tokens": 2023,
                "config_context_length": 8000,
            }
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        card = json.loads(proc.stdout)["cards"][0]
        footer = next(
            element["text"]["content"]
            for element in card["body"]["elements"]
            if element["tag"] == "div" and element["text"]["tag"] == "lark_md"
        )
        self.assertIn("输入 1.2k", footer)
        self.assertIn("输出 56", footer)
        self.assertIn("缓存读 789", footer)
        self.assertNotIn("999999", footer)
        self.assertNotIn("888888", footer)
        self.assertNotIn("777777", footer)


if __name__ == "__main__":
    unittest.main()
