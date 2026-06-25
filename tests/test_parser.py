from src.llm.parser import _extract_json, _sanitize_surrogates


class TestSanitizeSurrogates:
    def test_passes_clean_text(self):
        assert _sanitize_surrogates("hello world") == "hello world"

    def test_strips_surrogate_chars(self):
        assert "\ud800" not in _sanitize_surrogates("a\ud800b\udfffc")

    def test_handles_chinese_text(self):
        text = "玩家移动到坐标 (3, 0, 5)"
        assert _sanitize_surrogates(text) == text


class TestExtractJson:
    def test_extract_from_markdown_json_block(self):
        text = '```json\n{"key": "value"}\n```'
        result = _extract_json(text)
        assert result == '{"key": "value"}'

    def test_extract_from_markdown_block_no_lang(self):
        text = '```\n{"key": "value"}\n```'
        result = _extract_json(text)
        assert result == '{"key": "value"}'

    def test_extract_raw_json_object(self):
        text = '{"action_type": "move", "target_position": {"x": 1, "y": 2}}'
        result = _extract_json(text)
        assert result == text

    def test_extract_json_from_surrounding_text(self):
        text = '前缀内容\n{"name": "test"}\n后缀内容'
        result = _extract_json(text)
        assert result == '{"name": "test"}'

    def test_extract_nested_json_object(self):
        text = '{"outer": {"inner": [1, 2, 3]}}'
        result = _extract_json(text)
        assert result == text

    def test_extract_json_with_array(self):
        text = '{"items": [{"a": 1}, {"b": 2}]}'
        result = _extract_json(text)
        assert result == text

    def test_extract_json_with_unicode(self):
        text = '{"name": "艾琳", "feeling": "开心"}'
        result = _extract_json(text)
        assert result == text

    def test_extract_first_json_when_multiple(self):
        text = '{"first": 1} some text {"second": 2}'
        result = _extract_json(text)
        # Finds first { and last }, so effectively the whole span
        assert result == text

    def test_no_braces_returns_raw_text(self):
        text = "plain text without braces"
        result = _extract_json(text)
        assert result == text

    def test_handles_whitespace_only(self):
        text = "   \n  \t  "
        result = _extract_json(text)
        assert result == text.strip()
