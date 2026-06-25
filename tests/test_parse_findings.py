import json

import pytest

from astrbot_plugin_channel_inspect.review_service import ReviewFinding, ReviewService


@pytest.fixture
def service(config, context, storage, cli):
    return ReviewService(context, config, storage, cli)


class TestExtractJsonArray:
    def test_code_block_json(self, service):
        text = '```json\n[{"feed_id": "123", "risk_level": "high"}]\n```'
        assert service._extract_json_array(text) == '[{"feed_id": "123", "risk_level": "high"}]'

    def test_code_block_no_lang(self, service):
        text = '```\n[{"feed_id": "123"}]\n```'
        assert service._extract_json_array(text) == '[{"feed_id": "123"}]'

    def test_code_block_object(self, service):
        text = '```json\n{"feed_id": "123", "risk_level": "high"}\n```'
        assert service._extract_json_array(text) == '{"feed_id": "123", "risk_level": "high"}'

    def test_bare_array(self, service):
        text = 'some text [{"feed_id": "123"}] trailing'
        assert service._extract_json_array(text) == '[{"feed_id": "123"}]'

    def test_bare_object(self, service):
        text = 'text {"feed_id": "123"} end'
        assert service._extract_json_array(text) == '{"feed_id": "123"}'

    def test_empty(self, service):
        assert service._extract_json_array("") == "[]"
        assert service._extract_json_array("   ") == "[]"
        assert service._extract_json_array("没有json") == "[]"


class TestCleanupJsonCandidate:
    def test_smart_quotes(self, service):
        result = service._cleanup_json_candidate('{"feed_id": "123", "reason": "违规"}')
        assert result == '[{"feed_id": "123", "reason": "违规"}]'

    def test_trailing_commas(self, service):
        result = service._cleanup_json_candidate('[{"feed_id": "123",}]')
        assert result == '[{"feed_id": "123"}]'

    def test_wrap_object_in_array(self, service):
        result = service._cleanup_json_candidate('{"feed_id": "123"}')
        assert result == '[{"feed_id": "123"}]'

    def test_bom_strip(self, service):
        result = service._cleanup_json_candidate('\ufeff[{"feed_id": "123"}]')
        assert result == '[{"feed_id": "123"}]'

    def test_noop(self, service):
        result = service._cleanup_json_candidate('[{"feed_id": "123"}]')
        assert result == '[{"feed_id": "123"}]'


class TestNormalizeFindings:
    def test_string_list(self, service):
        data = ["feed_1", "feed_2"]
        result = service._normalize_findings(data)
        assert len(result) == 2
        assert result[0].feed_id == "feed_1"
        assert result[0].risk_level == "high"
        assert result[1].feed_id == "feed_2"

    def test_dict_list(self, service):
        data = [
            {"feed_id": "1", "risk_level": "high", "reason": "违规"},
            {"feed_id": "2", "risk_level": "low", "reason": "轻微"},
        ]
        result = service._normalize_findings(data)
        assert len(result) == 2
        assert result[0].feed_id == "1"
        assert result[0].risk_level == "high"
        assert result[0].reason == "违规"
        assert result[1].feed_id == "2"
        assert result[1].risk_level == "low"

    def test_single_object(self, service):
        data = {"feed_id": "1", "risk_level": "medium"}
        result = service._normalize_findings(data)
        assert len(result) == 1
        assert result[0].feed_id == "1"
        assert result[0].risk_level == "medium"

    def test_empty_list(self, service):
        assert service._normalize_findings([]) == []

    def test_missing_feed_id(self, service):
        data = [{"risk_level": "high"}]
        assert service._normalize_findings(data) == []

    def test_alternate_keys(self, service):
        data = [{"feedId": "1"}, {"id": "2"}]
        result = service._normalize_findings(data)
        assert len(result) == 2
        assert result[0].feed_id == "1"
        assert result[1].feed_id == "2"


class TestParseFindings:
    def test_full_pipeline(self, service):
        text = '```json\n[{"feed_id": "123", "risk_level": "high", "reason": "广告"}]\n```'
        result = service._parse_findings(text)
        assert len(result) == 1
        assert result[0].feed_id == "123"
        assert result[0].risk_level == "high"
        assert result[0].reason == "广告"

    def test_empty_json(self, service):
        assert service._parse_findings("[]") == []

    def test_malformed_json(self, service):
        result = service._parse_findings("{{{broken}")
        assert result == []

    def test_string_fallback(self, service):
        text = '["feed_1", "feed_2"]'
        result = service._parse_findings(text)
        assert len(result) == 2
        assert result[0].feed_id == "feed_1"
        assert result[1].feed_id == "feed_2"
