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


def test_media_parser_bracket_tags_do_not_override_series_title():
    parser = MediaParser()

    path = "/dav/302/133quark302/电视剧/华语/入青云[60帧率版本][全36集][国语配音+中文字幕].Love.in.the.Clouds.S01.2025.2160p.WEB-DL.H265.60fps(1).AAC-BlackTV/Love.in.the.Clouds.S01E03.2025.2160p.WEB-DL.H265.60fps.AAC-BlackTV.mkv"
    info = parser.parse(path, strict_episode=parser.should_force_episode(path))

    assert info.get("title") == "入青云"
    assert info.get("type") == "episode"
    assert info.get("season") == 1
    assert info.get("episode") == 3
    assert info.get("year") == 2025


def test_media_parser_site_promo_dir_does_not_override_title():
    parser = MediaParser()

    path = "/dav/302/133quark302/电视剧/华语/掌心.2160p.60fps.电影港 地址发布页 www.dygang.me 收藏不迷路/掌心.S01E01.2160p.60fps.WEB-DL.H265.AAC.mkv"
    info = parser.parse(path, strict_episode=parser.should_force_episode(path))

    assert info.get("title") == "掌心"
    assert info.get("type") == "episode"
    assert info.get("season") == 1
    assert info.get("episode") == 1


def test_media_parser_ignores_quality_subdir_as_title_hint():
    parser = MediaParser()

    path = "/dav/302/133quark302/电视剧/华语/大生意人（2025）/4K SDR/03 4K.mkv"
    info = parser.parse(path, strict_episode=parser.should_force_episode(path))

    assert info.get("title") == "大生意人"
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


def test_media_parser_variety_issue_with_phase_and_upper_part():
    parser = MediaParser()

    path = "/dav/302/133quark302/综艺/现在就出发/S03/2025.11.08-第3期上.mp4"
    info = parser.parse(path, strict_episode=parser.should_force_episode(path))

    assert info.get("title") == "现在就出发"
    assert info.get("type") == "episode"
    assert info.get("season") == 3
    assert info.get("episode") == 3
    assert info.get("part") == 1


def test_media_parser_guessit_thread_safety_under_concurrency():
    from concurrent.futures import ThreadPoolExecutor, as_completed

    parser = MediaParser()
    path = "牧神记.Tales.of.Qin.Mu.S01E58.2024.2160p.WEB-DL.H265.AAC.mp4"
    strict = parser.should_force_episode(path)

    def _work(_: int):
        info = parser.parse(path, strict_episode=strict)
        assert info.get("title") == "牧神记"
        assert info.get("type") == "episode"
        assert info.get("season") == 1
        assert info.get("episode") == 58

    with ThreadPoolExecutor(max_workers=16) as ex:
        futures = [ex.submit(_work, i) for i in range(800)]
        for fut in as_completed(futures):
            fut.result()
