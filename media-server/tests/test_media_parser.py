import pytest

from utils.media_parser import MediaParser


def test_media_parser_variety_show_path_parses_cleanly():
    parser = MediaParser()

    path = "/dav/302/133quark302/综艺/现在就出发/S01/2023.S01E10.Part2.1080p.WEB-DL.HEVC.DDP.2Audios.mp4"
    info = parser.parse(path, strict_episode=parser.should_force_episode(path))

    assert info.get("title") == "现在就出发"
    assert info.get("type") == "episode"
    assert info.get("season") == 1
    assert info.get("episode") == 10
    assert info.get("part") == 2


def test_media_parser_anime_dot_path_extracts_episode_number():
    parser = MediaParser()

    path = "dav.302.133quark302.动画.完美世界.101~200.完美世界 第149话 1080P(高清SDR)_Tacit0924.mp4"
    info = parser.parse(path, strict_episode=parser.should_force_episode(path))

    assert info.get("title") == "完美世界"
    assert info.get("type") == "episode"
    assert info.get("season") == 1
    assert info.get("episode") == 149


def test_media_parser_title_and_year_from_bracket_dir():
    parser = MediaParser()

    path = "/dav/302/133quark302/电视剧/华语/天地剑心(2025)/03 4K.mkv"
    info = parser.parse(path, strict_episode=parser.should_force_episode(path))

    assert info.get("title") == "天地剑心"
    assert info.get("type") == "episode"
    assert info.get("season") == 1
    assert info.get("episode") == 3
    assert info.get("year") == 2025


def test_media_parser_ignores_range_dir_and_4k_as_title():
    parser = MediaParser()

    path = "/dav/302/133quark302/动画/斗罗大陆1【4K】全253集/1-255【4K】/斗罗大陆S01E141.mp4"
    info = parser.parse(path, strict_episode=parser.should_force_episode(path))

    assert info.get("title") == "斗罗大陆"
    assert info.get("type") == "episode"
    assert info.get("season") == 1
    assert info.get("episode") == 141


def test_media_parser_sub_series_title_and_season_from_path():
    parser = MediaParser()

    path = "/dav/302/133quark302/电视剧/华语/唐朝诡事录/唐朝诡事录之西行S02/4K/22 4K.mkv"
    info = parser.parse(path, strict_episode=parser.should_force_episode(path))

    assert info.get("title") == "唐朝诡事录之西行"
    assert info.get("type") == "episode"
    assert info.get("season") == 2
    assert info.get("episode") == 22


@pytest.mark.parametrize(
    "path,expected_title,expected_episode",
    [
        ("/dav/动画/完美世界/完美世界 第1话.mp4", "完美世界", 1),
        ("/dav/动画/完美世界/完美世界 第12集 1080p.mp4", "完美世界", 12),
        ("/dav/综艺/现在就出发/S01/现在就出发.S01E02.mp4", "现在就出发", 2),
    ],
)
def test_media_parser_episode_hints_cover_common_chinese_patterns(path, expected_title, expected_episode):
    parser = MediaParser()
    info = parser.parse(path, strict_episode=parser.should_force_episode(path))

    assert info.get("title") == expected_title
    assert info.get("type") == "episode"
    assert info.get("episode") == expected_episode
