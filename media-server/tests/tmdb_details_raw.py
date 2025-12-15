import sys, asyncio
from typing import Optional

sys.path.append(str(__file__).split('/media-server/')[0] + '/media-server')

from services.scraper.tmdb import TmdbScraper
from services.scraper.base import MediaType


async def details_raw(provider_id: str, media_type: str, language: Optional[str] = None):
    s = TmdbScraper()
    await s.startup()
    try:
        mt = MediaType(media_type)
        lang = language or s.default_language
        auth = s._auth()
        params = {**auth['params'], 'language': lang,"append_to_response": "external_ids,images,credits"}
        if mt == MediaType.MOVIE:
            url = f"{s._base_url}/movie/{provider_id}"
        else:
            url = f"{s._base_url}/tv/{provider_id}"
        async with await s._get(url, params=params, headers=auth['headers']) as resp:
            data = await resp.json()
            import json
            print(json.dumps(data, ensure_ascii=False))
    finally:
        await s.shutdown()


def main():
    import argparse
    p = argparse.ArgumentParser(description='TMDB 原始详情 JSON 输出')
    p.add_argument('provider_id', type=str)
    p.add_argument('media_type', type=str, choices=[MediaType.MOVIE.value, MediaType.TV_SERIES.value, MediaType.TV_SEASON.value])
    p.add_argument('--language', type=str, default=None)
    a = p.parse_args()
    asyncio.run(details_raw(a.provider_id, a.media_type, a.language))


if __name__ == '__main__':
    main()
