import sys, asyncio

sys.path.append(str(__file__).split('/media-server/')[0] + '/media-server')

from services.scraper.tmdb import TmdbScraper


async def episode_raw(series_id: str, season_number: int, episode_number: int, language: str = None):
    s = TmdbScraper()
    await s.startup()
    try:
        lang = language or s.default_language
        auth = s._auth()
        params = {**auth['params'], 'language': lang,"append_to_response": "external_ids,images,credits"}
        url = f"{s._base_url}/tv/{series_id}/season/{season_number}/episode/{episode_number}"
        async with await s._get(url, params=params, headers=auth['headers']) as resp:
            data = await resp.json()
            import json
            print(json.dumps(data, ensure_ascii=False))
    finally:
        await s.shutdown()


def main():
    import argparse
    p = argparse.ArgumentParser(description='TMDB 原始集 JSON 输出')
    p.add_argument('series_id', type=str)
    p.add_argument('season_number', type=int)
    p.add_argument('episode_number', type=int)
    p.add_argument('--language', type=str, default=None)
    a = p.parse_args()
    asyncio.run(episode_raw(a.series_id, a.season_number, a.episode_number, a.language))


if __name__ == '__main__':
    main()
