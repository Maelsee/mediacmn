"""
豆瓣刮削器插件
"""
import asyncio
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
from bs4 import BeautifulSoup

from .base import ArtworkType, CreditType, MediaType, ScraperArtwork, ScraperCredit, ScraperExternalId, ScraperPlugin, ScraperSearchResult, ScraperMovieDetail, ScraperSeriesDetail, ScraperSeasonDetail, ScraperEpisodeDetail

logger = logging.getLogger(__name__)


class DoubanScraper(ScraperPlugin):
    """豆瓣刮削器插件"""
    
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    @property
    def name(self) -> str:
        return "douban"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def description(self) -> str:
        return "豆瓣电影刮削器"
    
    @property
    def supported_media_types(self) -> List[MediaType]:
        return [MediaType.MOVIE]  # 豆瓣主要支持电影
    
    @property
    def default_language(self) -> str:
        return "zh-CN"
    
    @property
    def priority(self) -> int:
        return 90  # 略低于TMDB
    
    def _get_session(self) -> aiohttp.ClientSession:
        """获取HTTP会话"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session
    
    async def test_connection(self) -> bool:
        """测试连接"""
        try:
            async with self._get_session() as session:
                url = "https://movie.douban.com/"
                async with session.get(url) as response:
                    if response.status == 200:
                        text = await response.text()
                        if "豆瓣电影" in text:
                            logger.info("豆瓣连接测试成功")
                            return True
                    
                    logger.error(f"豆瓣连接测试失败: HTTP {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"豆瓣连接测试异常: {e}")
            return False
    
    async def shutdown(self) -> None:
        try:
            if self._session and not self._session.closed:
                await self._session.close()
        except Exception:
            pass
    
    async def search(self, title: str, year: Optional[int] = None,
                    media_type: MediaType = MediaType.MOVIE,
                    language: str = "zh-CN") -> List[ScraperSearchResult]:
        """搜索媒体信息"""
        try:
            if media_type != MediaType.MOVIE:
                return []
            
            # 构建搜索URL
            search_query = title
            if year:
                search_query += f" {year}"
            
            search_url = f"https://movie.douban.com/subject_search"
            params = {
                "search_text": search_query,
                "cat": "1002"  # 电影分类
            }
            
            async with self._get_session() as session:
                async with session.get(search_url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"豆瓣搜索失败: HTTP {response.status}")
                        return []
                    
                    text = await response.text()
                    results = self._parse_search_results(text, title, year)
                    
                    logger.info(f"豆瓣搜索完成: {title} ({year}) -> {len(results)} 结果")
                    return results
                    
        except Exception as e:
            logger.error(f"豆瓣搜索异常: {e}")
            return []
    
    def _parse_search_results(self, html: str, original_title: str, year: Optional[int]) -> List[ScraperSearchResult]:
        """解析搜索结果"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            results = []
            
            # 查找电影条目
            movie_items = soup.find_all('div', class_='pl2')
            
            for item in movie_items[:10]:  # 只取前10个结果
                try:
                    # 获取标题和链接
                    title_link = item.find('a')
                    if not title_link:
                        continue
                    
                    title = title_link.get_text(strip=True)
                    href = title_link.get('href', '')
                    
                    # 提取豆瓣ID
                    douban_id = self._extract_douban_id(href)
                    if not douban_id:
                        continue
                    
                    # 获取年份和评分信息
                    info_div = item.find('p', class_='pl')
                    if info_div:
                        info_text = info_div.get_text(strip=True)
                        result_year = self._extract_year(info_text) or year
                        
                        # 评分
                        rating_span = item.find('span', class_='rating_nums')
                        rating = None
                        if rating_span:
                            try:
                                rating = float(rating_span.get_text(strip=True))
                            except:
                                pass
                        
                        # 检查年份匹配
                        if year and result_year and abs(result_year - year) > 1:
                            continue
                        
                        # 创建结果
                        result = ScraperSearchResult(
                            id=str(douban_id),
                            title=title,
                            original_name=None,
                            original_language=None,
                            release_date=None,
                            vote_average=rating,
                            provider=self.name,
                            media_type=MediaType.MOVIE.value,
                            poster_path=None,
                            backdrop_path=None,
                            year=result_year,
                            rating=rating,
                            provider_url=href
                        )
                        
                        results.append(result)
                        
                except Exception as e:
                    logger.warning(f"解析搜索结果项失败: {e}")
                    continue
            
            return results
            
        except Exception as e:
            logger.error(f"解析搜索结果失败: {e}")
            return []
    
    async def get_movie_details(self, movie_id: str, language: str = "zh-CN") -> Optional[ScraperMovieDetail]:
        """获取详细信息"""
        try:
            url = f"https://movie.douban.com/subject/{movie_id}/"
            
            async with self._get_session() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"豆瓣详情获取失败: HTTP {response.status}")
                        return None
                    
                    text = await response.text()
                    result = self._parse_movie_details(text, movie_id)
                    
                    if result:
                        logger.info(f"豆瓣详情获取完成: {movie_id}")
                    
                    return result
                
        except Exception as e:
            logger.error(f"豆瓣详情获取异常: {e}")
            return None

    async def get_series_details(self, series_id: str, language: str = "zh-CN") -> Optional[ScraperSeriesDetail]:
        return None

    async def get_season_details(self, series_id: str, season_number: int, language: str = "zh-CN") -> Optional[ScraperSeasonDetail]:
        return None

    async def get_episode_details(self, series_id: str, season_number: int, episode_number: int, language: str = "zh-CN") -> Optional[ScraperEpisodeDetail]:
        return None
    
    def _parse_movie_details(self, html: str, douban_id: str) -> Optional[ScraperMovieDetail]:
        """解析电影详情"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # 基本信息
            title = self._extract_title(soup)
            original_title = self._extract_original_title(soup)
            year = self._extract_year_from_title(soup)
            
            # 评分
            rating = self._extract_rating(soup)
            vote_count = self._extract_vote_count(soup)
            
            # 简介
            overview = self._extract_overview(soup)
            
            # 类型
            genres = self._extract_genres(soup)
            
            # 国家/地区
            countries = self._extract_countries(soup)
            
            # 语言
            languages = self._extract_languages(soup)
            
            # 时长
            runtime = self._extract_runtime(soup)
            
            # 上映日期
            release_date = self._extract_release_date(soup)
            
            # 演职员
            credits = self._extract_credits(soup)
            
            # 海报
            artworks = self._extract_artworks(soup, douban_id)
            
            # 外部ID
            external_ids = [
                ScraperExternalId(
                    provider="douban",
                    external_id=douban_id,
                    url=f"https://movie.douban.com/subject/{douban_id}/"
                )
            ]
            
            # IMDB ID（如果有）
            imdb_id = self._extract_imdb_id(soup)
            if imdb_id:
                external_ids.append(ScraperExternalId(
                    provider="imdb",
                    external_id=imdb_id,
                    url=f"https://www.imdb.com/title/{imdb_id}/"
                ))
            
            result = ScraperMovieDetail(
                movie_id=str(douban_id),
                title=title,
                original_title=original_title if original_title != title else None,
                original_language=(languages[0] if languages else None),
                overview=overview,
                release_date=release_date,
                runtime=runtime,
                tagline=None,
                genres=[g for g in genres or []],
                poster_path=(artworks[0].url if artworks else None),
                backdrop_path=None,
                vote_average=rating,
                vote_count=vote_count,
                imdb_id=None,
                status=None,
                belongs_to_collection=None,
                popularity=None,
                provider=self.name,
                provider_url=f"https://movie.douban.com/subject/{douban_id}/",
                artworks=artworks,
                credits=credits,
                external_ids=external_ids,
                raw_data={
                    "countries": countries,
                    "languages": languages,
                    "year": year,
                },
            )
            
            return result
            
        except Exception as e:
            logger.error(f"解析电影详情失败: {e}")
            return None
    
    def _extract_douban_id(self, url: str) -> Optional[str]:
        """提取豆瓣ID"""
        match = re.search(r'subject/(\d+)/', url)
        return match.group(1) if match else None
    
    def _extract_year(self, text: str) -> Optional[int]:
        """提取年份"""
        match = re.search(r'(\d{4})', text)
        if match:
            try:
                year = int(match.group(1))
                if 1900 <= year <= datetime.now().year + 5:
                    return year
            except:
                pass
        return None
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """提取标题"""
        # 尝试多个选择器
        title_selectors = [
            'h1 span[property="v:itemreviewed"]',
            'h1',
            'title'
        ]
        
        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(strip=True)
                # 清理标题（移除年份）
                text = re.sub(r'\(\d{4}\)', '', text).strip()
                if text:
                    return text
        
        return ""
    
    def _extract_original_title(self, soup: BeautifulSoup) -> Optional[str]:
        """提取原始标题"""
        # 查找副标题或别名
        aka_span = soup.find('span', class_='pl', text=re.compile(r'又名:'))
        if aka_span:
            aka_text = aka_span.next_sibling
            if aka_text:
                akas = [aka.strip() for aka in str(aka_text).split('/')]
                if akas:
                    return akas[0]
        
        return None
    
    def _extract_year_from_title(self, soup: BeautifulSoup) -> Optional[int]:
        """从标题中提取年份"""
        title_element = soup.select_one('h1 span[property="v:itemreviewed"]')
        if title_element:
            title_text = title_element.get_text(strip=True)
            return self._extract_year(title_text)
        return None
    
    def _extract_rating(self, soup: BeautifulSoup) -> Optional[float]:
        """提取评分"""
        rating_element = soup.select_one('strong[property="v:average"]')
        if rating_element:
            try:
                return float(rating_element.get_text(strip=True))
            except:
                pass
        return None
    
    def _extract_vote_count(self, soup: BeautifulSoup) -> Optional[int]:
        """提取评分人数"""
        votes_element = soup.select_one('span[property="v:votes"]')
        if votes_element:
            try:
                return int(votes_element.get_text(strip=True).replace(',', ''))
            except:
                pass
        return None
    
    def _extract_overview(self, soup: BeautifulSoup) -> Optional[str]:
        """提取简介"""
        summary_element = soup.select_one('span[property="v:summary"]')
        if summary_element:
            return summary_element.get_text(strip=True)
        
        # 备选选择器
        summary_element = soup.select_one('#link-report span.all')
        if summary_element:
            return summary_element.get_text(strip=True)
        
        return None
    
    def _extract_genres(self, soup: BeautifulSoup) -> List[str]:
        """提取类型"""
        genres = []
        genre_elements = soup.select('span[property="v:genre"]')
        for element in genre_elements:
            genre = element.get_text(strip=True)
            if genre:
                genres.append(genre)
        return genres
    
    def _extract_countries(self, soup: BeautifulSoup) -> List[str]:
        """提取国家/地区"""
        countries = []
        
        # 查找制片国家/地区
        country_text = None
        for text in soup.stripped_strings:
            if "制片国家/地区:" in text or "制片国家:" in text:
                country_text = text
                break
        
        if country_text:
            # 提取国家信息
            match = re.search(r'制片国家/?地区?:\s*([^\n]+)', country_text)
            if match:
                countries_str = match.group(1)
                countries = [country.strip() for country in countries_str.split('/')]
        
        return countries
    
    def _extract_languages(self, soup: BeautifulSoup) -> List[str]:
        """提取语言"""
        languages = []
        
        # 查找语言
        lang_text = None
        for text in soup.stripped_strings:
            if "语言:" in text:
                lang_text = text
                break
        
        if lang_text:
            # 提取语言信息
            match = re.search(r'语言:\s*([^\n]+)', lang_text)
            if match:
                langs_str = match.group(1)
                languages = [lang.strip() for lang in langs_str.split('/')]
        
        return languages
    
    def _extract_runtime(self, soup: BeautifulSoup) -> Optional[int]:
        """提取时长"""
        runtime_element = soup.select_one('span[property="v:runtime"]')
        if runtime_element:
            try:
                runtime_text = runtime_element.get_text(strip=True)
                # 提取分钟数
                match = re.search(r'(\d+)', runtime_text)
                if match:
                    return int(match.group(1))
            except:
                pass
        return None
    
    def _extract_release_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """提取上映日期"""
        date_element = soup.select_one('span[property="v:initialReleaseDate"]')
        if date_element:
            try:
                date_text = date_element.get_text(strip=True)
                # 提取日期
                match = re.search(r'(\d{4}-\d{1,2}-\d{1,2})', date_text)
                if match:
                    return datetime.strptime(match.group(1), "%Y-%m-%d").date()
            except:
                pass
        return None
    
    def _extract_credits(self, soup: BeautifulSoup) -> List[ScraperCredit]:
        """提取演职员信息"""
        credits = []
        
        # 导演
        director_elem = soup.find('span', class_='pl', text=re.compile(r'导演:'))
        if director_elem:
            director_links = director_elem.find_next_siblings('a')
            for link in director_links:
                director_name = link.get_text(strip=True)
                if director_name:
                    credits.append(ScraperCredit(
                        type=CreditType.DIRECTOR,
                        name=director_name
                    ))
        
        # 编剧
        writer_elem = soup.find('span', class_='pl', text=re.compile(r'编剧:'))
        if writer_elem:
            writer_links = writer_elem.find_next_siblings('a')
            for link in writer_links:
                writer_name = link.get_text(strip=True)
                if writer_name:
                    credits.append(ScraperCredit(
                        type=CreditType.WRITER,
                        name=writer_name
                    ))
        
        # 主演
        actor_elem = soup.find('span', class_='pl', text=re.compile(r'主演:'))
        if actor_elem:
            actor_links = actor_elem.find_next_siblings('a')
            for i, link in enumerate(actor_links[:10]):  # 只取前10个
                actor_name = link.get_text(strip=True)
                if actor_name:
                    credits.append(ScraperCredit(
                        type=CreditType.ACTOR,
                        name=actor_name,
                        order=i + 1
                    ))
        
        return credits
    
    def _extract_artworks(self, soup: BeautifulSoup, douban_id: str) -> List[ScraperArtwork]:
        """提取艺术作品"""
        artworks = []
        
        # 主海报
        poster_elem = soup.select_one('#mainpic img')
        if poster_elem:
            poster_url = poster_elem.get('src', '')
            if poster_url:
                artworks.append(ScraperArtwork(
                    type=ArtworkType.POSTER,
                    url=poster_url,
                    language="zh-CN"
                ))
        
        return artworks
    
    def _extract_imdb_id(self, soup: BeautifulSoup) -> Optional[str]:
        """提取IMDB ID"""
        # 查找IMDB链接
        for link in soup.find_all('a'):
            href = link.get('href', '')
            if 'imdb.com/title/' in href:
                match = re.search(r'title/(tt\d+)/', href)
                if match:
                    return match.group(1)
        return None
    
    def get_config_schema(self) -> Dict[str, any]:
        """获取配置模式"""
        return {
            "type": "object",
            "properties": {
                "timeout": {
                    "type": "integer",
                    "description": "请求超时时间（秒）",
                    "default": 30,
                    "minimum": 5,
                    "maximum": 300
                },
                "delay": {
                    "type": "integer", 
                    "description": "请求间隔（秒）",
                    "default": 1,
                    "minimum": 0,
                    "maximum": 10
                }
            },
            "required": []
        }
