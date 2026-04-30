## 弹幕api
post /api/danmu/match/auto
参数：
    title: Optional[str] = Field(..., description="视频标题")
    season: Optional[int] = Field(default=None, description="季数")
    episode: Optional[int] = Field(default=None, description="集数")
    file_id: Optional[str] = Field(default=None, description="文件ID")
    
返回数据：
```json
{
  "is_matched": true,
  "confidence": 1,
  "sources": [
    {
      "episodeId": 10168,
      "animeId": 279446,
      "animeTitle": "生万物(2025)【电视剧】from 听风",
      "episodeTitle": "【qiyi】 第2集",
      "type": "电视剧",
      "typeDescription": "电视剧",
      "shift": 0,
      "imageUrl": "http://pic8.iqiyipic.com/image/20250812/02/eb/a_100585021_m_601_m9_579_772.jpg"
    }
  ],
  "best_match": {
    "episodeId": 10168,
    "animeId": 279446,
    "animeTitle": "生万物(2025)【电视剧】from 听风",
    "episodeTitle": "【qiyi】 第2集",
    "type": "电视剧",
    "typeDescription": "电视剧",
    "shift": 0,
    "imageUrl": "http://pic8.iqiyipic.com/image/20250812/02/eb/a_100585021_m_601_m9_579_772.jpg"
  },
  "binding": {
    "id": 2,
    "file_id": "6971",
    "episode_id": "10168",
    "anime_id": "279446",
    "anime_title": "生万物(2025)【电视剧】from 听风",
    "episode_title": "【qiyi】 第2集",
    "type": "电视剧",
    "typeDescription": "电视剧",
    "imageUrl": "http://pic8.iqiyipic.com/image/20250812/02/eb/a_100585021_m_601_m9_579_772.jpg",
    "offset": 0,
    "is_manual": false,
    "match_confidence": 1
  },
  "danmu_data": {
    "episode_id": 10168,
    "count": 1482,
    "comments": [
      {
        "cid": 1,
        "p": "1.00,1,16707842,[qiyi]",
        "m": "大脚：下辈子定当兵练脚力 ️♡848",
        "t": 1
      },
      ...
    ],
    "offset": 0,
    "video_duration": 2739,
    "load_mode": "segment",
    "segment_list": [
      {
        "type": "qiyi",
        "segment_start": 0,
        "segment_end": 300,
        "url": "https://cmts.iqiyi.com/bullet/25/00/5164845083762500_300_1.z?rn=0.0123456789123456&business=danmu&is_iqiyi=true&is_video_page=true&tvid=5164845083762500&albumid=7730171462205101&categoryid=2&qypid=010102101000000000"
      },
    ...
    ],
    "binding": null
  }
}
```
post /api/danmu/search
参数：
{
  "keyword": "string",
  "type": "anime",
  "limit": 20
}
```json
{
  "keyword": "万物生",
  "type": "anime",
  "items": [
    {
      "animeId": 177883,
      "bangumiId": "177883",
      "animeTitle": "万物生灵 2(2025)【电视剧】from 听风",
      "type": "电视剧",
      "typeDescription": "电视剧",
      "imageUrl": "https://i0.hdslb.com/bfs/bangumi/image/fa91b0ad720b0c22addcf7227b2d3a0986d278da.png",
      "startDate": "2025-01-01T00:00:00Z",
      "episodeCount": 7,
      "rating": 0,
      "isFavorited": true,
      "source": "vod"
    },
    ...
  ],
  "has_more": false
}
```
get /api/danmu/bangumi/{anime_id}
参数：
{
  "anime_id": "string"
}
```json
{
  "animeId": 235508,
  "animeTitle": "长安的荔枝(2025)【电视剧】from 360",
  "type": "电视剧",
  "typeDescription": "电视剧",
  "imageUrl": "https://p.ssl.qhimg.com/d/dy_05b164e1748b78d4ef0772ac08088eb7.",
  "episodeCount": 0,
  "seasons": [
    {
      "id": "season-235508",
      "airDate": "2025-01-01T00:00:00Z",
      "name": "Season 1",
      "episodeCount": 35
    }
  ],
  "episodes": [
    {
      "seasonId": "season-235508",
      "episodeId": 10203,
      "episodeTitle": "【qq】 第1集",
      "episodeNumber": "1",
      "airDate": "2025-01-01T00:00:00Z"
    },
    ...
  ]
}
```
get /api/danmu/{episode_id}
参数：
{
  "episode_id": "string",
  "file_id": "string",
  "load_mode": "segment"或"full"
}
```json
{
  "episode_id": 10168,
  "count": 1482,
  "comments": [
    {
      "cid": 1,
      "p": "1.00,1,16707842,[qiyi]",
      "m": "大脚：下辈子定当兵练脚力 ️♡848",
      "t": 1
    },
  ],
  "offset": 0,
  "video_duration": 2739,
  "load_mode": "segment",
  "segment_list": [
    {
      "type": "qiyi",
      "segment_start": 0,
      "segment_end": 300,
      "url": "https://cmts.iqiyi.com/bullet/25/00/5164845083762500_300_1.z?rn=0.0123456789123456&business=danmu&is_iqiyi=true&is_video_page=true&tvid=5164845083762500&albumid=7730171462205101&categoryid=2&qypid=010102101000000000"
    }
  ],
  "binding": null
}
```
post /api/danmu/{episode_id}/next-segment
参数：
{
  "segment": {
    "type": "string",
    "segment_start": int,
    "segment_end": int,
    "url": "string"
  },
  "episode_id": optional("string"),
  "format": optional("json"/"xml")
}

```json
{
  "count": 1590,
  "comments": [
    {
      "cid": 1,
      "p": "2401.00,1,16777215,[qiyi]",
      "m": "都是那个时代枷锁 ️♡408",
      "t": 2401
    },
  ],
  "success": true,
  "errorCode": 0,
  "errorMessage": ""
}
```
/api/danmu/match/bind/{file_id}
```json
{
  "id": 2,
  "file_id": "6971",
  "episode_id": "10168",
  "anime_id": "279446",
  "anime_title": "生万物(2025)【电视剧】from 听风",
  "episode_title": "【qiyi】 第2集",
  "type": "电视剧",
  "typeDescription": "电视剧",
  "imageUrl": "http://pic8.iqiyipic.com/image/20250812/02/eb/a_100585021_m_601_m9_579_772.jpg",
  "offset": 0,
  "is_manual": false,
  "match_confidence": 1
}
```
/api/danmu/match/bind/{file_id}
```json
{
  "code": 0,
  "message": "Binding deleted successfully",
  "data": null
}
```
/api/danmu/match/bind/{file_id}/offset
```json
{
  "id": 2,
  "file_id": "6971",
  "episode_id": "10168",
  "anime_id": "279446",
  "anime_title": "生万物(2025)【电视剧】from 听风",
  "episode_title": "【qiyi】 第2集",
  "type": "电视剧",
  "typeDescription": "电视剧",
  "imageUrl": "http://pic8.iqiyipic.com/image/20250812/02/eb/a_100585021_m_601_m9_579_772.jpg",
  "offset": 1,
  "is_manual": false,
  "match_confidence": 1
}