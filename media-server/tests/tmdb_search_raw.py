import sys, asyncio
from typing import Optional

# 保证可直接运行：追加 media-server 到 sys.path
sys.path.append(str(__file__).split('/media-server/')[0] + '/media-server')

from services.scraper.tmdb import TmdbScraper
from services.scraper.base import MediaType


async def search_raw(title: str, year: Optional[int], media_type: str):
    s = TmdbScraper()
    await s.startup()
    try:
        mt = MediaType(media_type)
        auth = s._auth()  # 使用插件的认证
        params = {**auth["params"], "language": s.default_language, "query": title}
        if year is not None:
            if mt == MediaType.MOVIE:
                params["year"] = year
            else:
                params["first_air_date_year"] = year
        url = f"{s._base_url}/search/movie" if mt == MediaType.MOVIE else f"{s._base_url}/search/tv"
        async with await s._get(url, params=params, headers=auth["headers"]) as resp:
            data = await resp.json()
            import json
            print(json.dumps(data, ensure_ascii=False))
    finally:
        await s.shutdown()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TMDB 原始搜索JSON输出")
    parser.add_argument("title", type=str)
    parser.add_argument("media_type", type=str, choices=[m.value for m in MediaType])
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(search_raw(args.title, args.year, args.media_type))


if __name__ == "__main__":
    main()
