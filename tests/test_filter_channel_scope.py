import pytest

from astrbot_plugin_channel_inspect.review_service import ReviewService


@pytest.fixture
def service(config, context, storage, cli):
    return ReviewService(context, config, storage, cli)


@pytest.fixture
def feeds():
    return [
        {"feed_id": "1", "channel_id": "ch_a"},
        {"feed_id": "2", "channel_id": "ch_b"},
        {"feed_id": "3", "channel_id": "ch_c"},
        {"feed_id": "4", "channel_id": ""},
        {"feed_id": "5"},
    ]


class TestFilterChannelScope:
    def test_no_filter(self, service, feeds):
        result = service._filter_channel_scope(feeds)
        assert len(result) == 5

    def test_exclude_channels(self, service, feeds, config):
        config.channel.exclude_channel_ids = ["ch_a", "ch_c"]
        result = service._filter_channel_scope(feeds)
        assert len(result) == 3
        assert all(f["feed_id"] in ("2", "4", "5") for f in result)

    def test_target_channels(self, service, feeds, config):
        config.channel.target_channel_ids = ["ch_a", "ch_b"]
        result = service._filter_channel_scope(feeds)
        assert len(result) == 4
        assert all(f["feed_id"] in ("1", "2", "4", "5") for f in result)

    def test_target_empty_scan_all_false(self, service, feeds, config):
        config.channel.target_channel_ids = []
        config.channel.scan_all_when_target_empty = False
        result = service._filter_channel_scope(feeds)
        assert len(result) == 2
        assert all(f["feed_id"] in ("4", "5") for f in result)

    def test_target_empty_scan_all_true(self, service, feeds, config):
        config.channel.target_channel_ids = []
        config.channel.scan_all_when_target_empty = True
        result = service._filter_channel_scope(feeds)
        assert len(result) == 5

    def test_target_and_exclude(self, service, feeds, config):
        config.channel.target_channel_ids = ["ch_a", "ch_b", "ch_c"]
        config.channel.exclude_channel_ids = ["ch_b"]
        result = service._filter_channel_scope(feeds)
        assert len(result) == 4
        assert all(f["feed_id"] in ("1", "3", "4", "5") for f in result)

    def test_empty_feeds(self, service):
        assert service._filter_channel_scope([]) == []
