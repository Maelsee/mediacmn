"""
WebDAV存储客户端实现

基于WebDAV协议直接实现统一的StorageClient接口，不依赖旧模块
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any, Iterator
from datetime import datetime
import aiohttp
from urllib.parse import urljoin, urlparse, quote, unquote
import xml.etree.ElementTree as ET

from ..storage_client import (
    StorageClient, StorageEntry, StorageInfo, 
    StorageConnectionError, StorageNotFoundError, StoragePermissionError, StorageError
)

logger = logging.getLogger(__name__)


class WebDAVStorageClient(StorageClient):
    """WebDAV存储客户端"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        # 获取基础配置
        base_url = config.get('url', '').rstrip('/')
        root_path = config.get('root_path', '').strip('/')
        # 组合完整的 base_url
        if root_path:
            self._base_url = f"{base_url}/{root_path}"
        else:
            self._base_url = base_url

        self._session: Optional[aiohttp.ClientSession] = None
        self._username = config.get('username', '')
        self._password = config.get('password', '')
        self._timeout = config.get('timeout', 30)
        self._verify_ssl = config.get('verify_ssl', True)
        self._connected = False

    async def connect(self) -> bool:
        """建立WebDAV连接"""
        # 如果已经连接且会话有效，直接返回
        if self._connected and self._session and not self._session.closed:
            return True

        # 如果存在旧会话，先关闭
        if self._session:
            await self._session.close()
            self._session = None

        try:
            # 创建HTTP会话
            connector = aiohttp.TCPConnector(
                ssl=False if not self._verify_ssl else None,
                limit=100,
                limit_per_host=30
            )
            
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                auth=aiohttp.BasicAuth(self._username, self._password) if self._username else None
            )
            
            # 测试连接
            success, error = await self.check_connection()
            if not success:
                # 连接失败，关闭会话
                await self._session.close()
                self._session = None
                raise StorageConnectionError(error or "连接测试失败")
            
            self._connected = True
            logger.debug(f"WebDAV存储客户端已连接: {self.name}")
            return True
            
        except Exception as e:
            # 发生异常，确保会话关闭
            if self._session:
                await self._session.close()
                self._session = None
            self._connected = False
            logger.error(f"WebDAV连接失败: {e}")
            raise StorageConnectionError(f"WebDAV连接失败: {e}")
    
    async def disconnect(self) -> None:
        """断开WebDAV连接"""
        if self._session:
            await self._session.close()
            self._session = None
        self._connected = False
        logger.debug(f"WebDAV存储客户端已断开: {self.name}")
    
    def _parse_webdav_response(self, xml_text: str) -> List[Dict[str, Any]]:
        """解析WebDAV PROPFIND响应"""
        entries = []
        try:
            root = ET.fromstring(xml_text)
            # 处理命名空间
            ns = {
                'd': 'DAV:',
                'DAV': 'DAV:'
            }
            
            for response in root.findall('.//d:response', ns):
                entry = {}
                
                # 获取href (路径)
                href_elem = response.find('d:href', ns)
                if href_elem is not None and href_elem.text:
                    # URL解码处理
                    import urllib.parse
                    decoded_href = urllib.parse.unquote(href_elem.text)
                    entry['path'] = urlparse(decoded_href).path
                    entry['name'] = entry['path'].rstrip('/').split('/')[-1] or '/'
                
                # 获取propstat信息
                propstat = response.find('d:propstat', ns)
                if propstat is not None:
                    prop = propstat.find('d:prop', ns)
                    if prop is not None:
                        # 获取资源类型
                        resourcetype = prop.find('d:resourcetype', ns)
                        if resourcetype is not None:
                            entry['is_dir'] = resourcetype.find('d:collection', ns) is not None
                        else:
                            entry['is_dir'] = False
                        
                        # 获取大小
                        getcontentlength = prop.find('d:getcontentlength', ns)
                        if getcontentlength is not None and getcontentlength.text:
                            try:
                                entry['size'] = int(getcontentlength.text)
                            except (ValueError, TypeError):
                                entry['size'] = 0
                        else:
                            entry['size'] = 0 if entry.get('is_dir') else None
                        
                        # 获取修改时间
                        getlastmodified = prop.find('d:getlastmodified', ns)
                        if getlastmodified is not None and getlastmodified.text:
                            try:
                                # WebDAV日期格式通常是 RFC1123
                                entry['modified'] = datetime.strptime(
                                    getlastmodified.text, 
                                    '%a, %d %b %Y %H:%M:%S %Z'
                                )
                            except ValueError:
                                entry['modified'] = None
                        
                        # 获取内容类型
                        getcontenttype = prop.find('d:getcontenttype', ns)
                        if getcontenttype is not None and getcontenttype.text:
                            entry['content_type'] = getcontenttype.text
                        
                        # 获取ETag
                        getetag = prop.find('d:getetag', ns)
                        if getetag is not None and getetag.text:
                            entry['etag'] = getetag.text.strip('"')
                
                if entry:
                    entries.append(entry)
                    
        except ET.ParseError as e:
            logger.warning(f"XML解析错误: {e}")
            
        return entries

    async def check_connection(self) -> tuple[bool, Optional[str]]:
        """测试WebDAV连接"""
        if not self._session:
            return False, "HTTP会话未初始化"
        
        try:
            # 发送PROPFIND请求测试连接
            url = self._base_url
            headers = {
                'Depth': '0',
                'Content-Type': 'application/xml'
            }
            
            # 空的PROPFIND请求体
            body = """<?xml version="1.0" encoding="utf-8"?>
            <D:propfind xmlns:D="DAV:">
            <D:prop>
                <D:resourcetype/>
            </D:prop>
            </D:propfind>"""
            
            async with self._session.request('PROPFIND', url, headers=headers, data=body) as response:
                if response.status in [200, 207]:  # 207 Multi-Status 是PROPFIND的正常响应
                    return True, None
                elif response.status == 401:
                    return False, "认证失败"
                elif response.status == 403:
                    return False, "权限不足"
                else:
                    return False, f"连接测试失败: HTTP {response.status}"
                    
        except Exception as e:
            error_msg = f"连接测试异常: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    async def info(self, path: str = "/") -> StorageInfo:
        """获取WebDAV系统信息"""
        # WebDAV协议本身不直接提供空间信息，返回基础信息
        return StorageInfo(
            readonly=False,
            supports_resume=True,
            supports_range=True,
            max_file_size=None
        )
    
    def replace_base_path(self, base_url: str, path: str) -> str:
        """替换路径中的基础路径"""
        parsed = urlparse(base_url)
        if path.startswith(parsed.path):
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            return f"{base_url}/{quote(path.strip('/'))}"
        return f"{base_url}/{quote(path.strip('/'))}"

    async def list_dir(self, path: str = "/", depth: int = 1) -> List[StorageEntry]:
        """列出WebDAV目录内容"""
        if not self._session:
            raise StorageConnectionError("客户端未连接")
        # logger.info(f'----查看输入路径: {path}')
        try:
            # 构建完整的URL
            base_url = self._base_url.rstrip('/')
            url = self.replace_base_path(base_url, path)
            # logger.info(f'----查看URL: {url}')
            # encoded_path = quote(path.strip('/'))
            # url = f"{base_url}/{encoded_path}"
            
            depth = "infinity" if depth > 1 else str(depth)
            # 设置请求头
            headers = {
                'Depth': depth,
                'Content-Type': 'application/xml'
            }
            
            # PROPFIND请求体
            body = """<?xml version="1.0" encoding="utf-8"?>
                <D:propfind xmlns:D="DAV:">
                <D:prop>
                    <D:displayname/>
                    <D:getcontentlength/>
                    <D:getlastmodified/>
                    <D:resourcetype/>
                    <D:getcontenttype/>
                    <D:getetag/>
                </D:prop>
                </D:propfind>"""
                        
            async with self._session.request('PROPFIND', url, headers=headers, data=body) as response:
                # logger.info(f'webdav协议文件信息响应状态: {response}')

                if response.status == 207:  # Multi-Status
                    xml_content = await response.text()
                    # logger.info(f'----查看XML内容: {xml_content}')

                    entries = self._parse_webdav_response(xml_content)
                    
                    # 转换为统一的StorageEntry格式
                    storage_entries = []
                    for entry in entries:
                        # 跳过当前目录本身和根目录
                        # logger.info(f'----查看结果: {entry.get('path').rstrip('/')}，输入路径: {unquote(urlparse(url).path.rstrip('/'))}')
                        if entry.get('path').rstrip('/') == unquote(urlparse(url).path.rstrip('/')):
                            continue
                            
                        storage_entry = StorageEntry(
                            name=entry.get('name', ''),
                            path=entry.get('path', ''),
                            is_dir=entry.get('is_dir', False),
                            size=entry.get('size'),
                            modified=entry.get('modified'),
                            content_type=entry.get('content_type'),
                            etag=entry.get('etag')
                        )
                        storage_entries.append(storage_entry)
                    
                    return storage_entries
                    
                elif response.status == 404:
                    raise StorageNotFoundError(f"路径不存在: {path}", path)
                elif response.status == 403:
                    raise StoragePermissionError(f"权限不足: {path}", path)
                else:
                    error_text = await response.text()
                    raise StorageError(f"列出目录失败: HTTP {response.status} - {error_text}")
                    
        except Exception as e:
            error_msg = f"列出目录失败: {e}"
            logger.error(error_msg)
            
            if isinstance(e, (StorageNotFoundError, StoragePermissionError, StorageError)):
                raise
            else:
                raise StorageError(error_msg)
    
    async def stat(self, path: str) -> StorageEntry:
        """获取文件/目录信息（兼容旧接口）"""
        return await self.get_file_info(path)
    
    async def get_file_info(self, path: str) -> StorageEntry:
        """获取WebDAV文件/目录详细信息"""
        if not self._session:
            raise StorageConnectionError("客户端未连接")
        
        try:
            logger.info(f'获取文件信息 - 输入路径: {path}')
            logger.info(f'基础URL: {self._base_url}')
            
            # 使用与list_dir相同的路径处理逻辑
            base_url = self._base_url.rstrip('/')
            url = self.replace_base_path(base_url, path)
            logger.info(f'修正后的URL: {url}')
            
            # 设置请求头
            headers = {
                'Depth': '0',
                'Content-Type': 'application/xml'
            }
            
            # PROPFIND请求体
            body = """<?xml version="1.0" encoding="utf-8"?>
            <D:propfind xmlns:D="DAV:">
            <D:prop>
                <D:displayname/>
                <D:getcontentlength/>
                <D:getlastmodified/>
                <D:resourcetype/>
                <D:getcontenttype/>
                <D:getetag/>
            </D:prop>
            </D:propfind>"""
            
            async with self._session.request('PROPFIND', url, headers=headers, data=body) as response:
                logger.info(f'webdav协议单文件信息响应状态: {response}')

                if response.status == 207:  # Multi-Status
                    xml_content = await response.text()
                    entries = self._parse_webdav_response(xml_content)
                    
                    if entries:
                        entry = entries[0]  # 只返回第一个条目
                        return StorageEntry(
                            name=entry.get('name', path.split('/')[-1]),
                            path=path,
                            is_dir=entry.get('is_dir', False),
                            size=entry.get('size'),
                            modified=entry.get('modified'),
                            content_type=entry.get('content_type'),
                            etag=entry.get('etag')
                        )
                    else:
                        raise StorageNotFoundError(f"路径不存在: {path}", path)
                        
                elif response.status == 404:
                    raise StorageNotFoundError(f"路径不存在: {path}", path)
                elif response.status == 403:
                    raise StoragePermissionError(f"权限不足: {path}", path)
                else:
                    error_text = await response.text()
                    raise StorageError(f"获取文件信息失败: HTTP {response.status} - {error_text}")
                    
        except Exception as e:
            error_msg = f"获取文件信息失败: {e}"
            logger.error(error_msg)
            
            if isinstance(e, (StorageNotFoundError, StoragePermissionError, StorageError)):
                raise
            else:
                raise StorageError(error_msg)
    
    async def download_iter(self, path: str, chunk_size: int = 64 * 1024, offset: int = 0) -> Iterator[bytes]:
        """流式下载WebDAV文件"""
        if not self._session:
            raise StorageConnectionError("客户端未连接")
        
        try:
            # 使用与get_file_info相同的路径处理逻辑
            base_url = self._base_url.rstrip('/')
            url = self.replace_base_path(base_url, path)
            
            # 设置请求头，支持断点续传
            headers = {}
            if offset > 0:
                headers['Range'] = f'bytes={offset}-'
            
            async with self._session.get(url, headers=headers) as response:
                if response.status == 200:
                    async for chunk in response.content.iter_chunked(chunk_size):
                        yield chunk
                elif response.status == 404:
                    raise StorageNotFoundError(f"文件不存在: {path}", path)
                elif response.status == 403:
                    raise StoragePermissionError(f"下载权限不足: {path}", path)
                else:
                    error_text = await response.text()
                    raise StorageError(f"下载失败: HTTP {response.status} - {error_text}")
                    
        except Exception as e:
            error_msg = f"下载文件失败: {e}"
            logger.error(error_msg)
            
            if isinstance(e, (StorageNotFoundError, StoragePermissionError, StorageError)):
                raise
            else:
                raise StorageError(error_msg)
    
    async def upload(self, path: str, data: bytes, 
                    content_type: Optional[str] = None) -> bool:
        """上传文件到WebDAV"""
        if not self._session:
            raise StorageConnectionError("客户端未连接")
        
        try:
            # 构建完整的URL
            # base_url = self._base_url.rstrip('/')
            # encoded_path = quote(path.strip('/'))
            # url = f"{base_url}/{encoded_path}"
            base_url = self._base_url.rstrip('/')
            url = self.replace_base_path(base_url, path)
            
            # 设置请求头
            headers = {}
            if content_type:
                headers['Content-Type'] = content_type
            
            async with self._session.put(url, data=data, headers=headers) as response:
                if response.status in [200, 201, 204]:  # 成功创建/更新
                    logger.info(f"文件上传成功: {path}")
                    return True
                elif response.status == 405:  # Method Not Allowed，文件已存在或其他限制
                    error_text = await response.text()
                    logger.warning(f"WebDAV上传返回405，尝试其他方法或文件已存在: {path} - {error_text}")
                    # 某些WebDAV服务器对PUT方法有限制，尝试检查文件是否存在
                    try:
                        if await self.exists(path):
                            logger.info(f"文件已存在，视为上传成功: {path}")
                            return True
                        else:
                            # 文件不存在但405，可能是服务器配置问题
                            logger.error(f"WebDAV服务器配置不支持PUT上传: {path}")
                            return False
                    except Exception as exist_check_error:
                        logger.warning(f"存在性检查失败，保守返回失败: {exist_check_error}")
                        return False
                elif response.status == 403:
                    raise StoragePermissionError(f"上传权限不足: {path}", path)
                else:
                    error_text = await response.text()
                    raise StorageError(f"上传失败: HTTP {response.status} - {error_text}")
                    
        except Exception as e:
            error_msg = f"上传文件失败: {e}"
            logger.error(error_msg)
            
            if isinstance(e, (StoragePermissionError, StorageError)):
                raise
            else:
                raise StorageError(error_msg)
    
    async def create_dir(self, path: str) -> bool:
        """在WebDAV中创建目录"""
        if not self._session:
            raise StorageConnectionError("客户端未连接")
        
        try:
            # 构建完整的URL
            # base_url = self._base_url.rstrip('/')
            # encoded_path = quote(path.strip('/'))
            # url = f"{base_url}/{encoded_path}"
            base_url = self._base_url.rstrip('/')
            url = self.replace_base_path(base_url, path)
            
            # WebDAV的MKCOL方法创建目录
            async with self._session.request('MKCOL', url) as response:
                if response.status == 201:  # 成功创建
                    logger.info(f"目录创建成功: {path}")
                    return True
                elif response.status == 405:  # Method Not Allowed，目录已存在
                    logger.info(f"目录已存在: {path}")
                    return True  # 视为成功
                elif response.status == 403:
                    raise StoragePermissionError(f"创建目录权限不足: {path}", path)
                elif response.status == 409:  # Conflict，父目录不存在
                    raise StorageError(f"父目录不存在: {path}")
                else:
                    error_text = await response.text()
                    raise StorageError(f"创建目录失败: HTTP {response.status} - {error_text}")
                    
        except Exception as e:
            error_msg = f"创建目录失败: {e}"
            logger.error(error_msg)
            
            if isinstance(e, (StoragePermissionError, StorageError)):
                raise
            else:
                raise StorageError(error_msg)
    
    async def delete(self, path: str) -> bool:
        """删除WebDAV文件或目录"""
        if not self._session:
            raise StorageConnectionError("客户端未连接")
        
        try:
            # WebDAV的DELETE方法
            if not self._session:
                raise StorageConnectionError("HTTP会话未初始化")
            
            # url = urljoin(self._base_url, path.lstrip('/'))
            # 构建完整的URL
            # base_url = self._base_url.rstrip('/')
            # encoded_path = quote(path.strip('/'))
            # url = f"{base_url}/{encoded_path}"
            base_url = self._base_url.rstrip('/')
            url = self.replace_base_path(base_url, path)
            
            async with self._session.delete(url) as response:
                if response.status in [200, 204]:  # 成功删除
                    logger.info(f"删除成功: {path}")
                    return True
                elif response.status == 404:  # 不存在
                    raise StorageNotFoundError(f"路径不存在: {path}", path)
                elif response.status == 403:  # 权限不足
                    raise StoragePermissionError(f"删除权限不足: {path}", path)
                else:
                    error_text = await response.text()
                    raise StorageError(f"删除失败: {response.status} - {error_text}")
                    
        except Exception as e:
            # 如果已经是StorageError的子类，直接抛出
            if isinstance(e, (StorageNotFoundError, StoragePermissionError, StorageError)):
                raise
            
            error_msg = f"删除失败: {e}"
            logger.error(error_msg)
            raise StorageError(error_msg)
    
    async def exists(self, path: str) -> bool:
        """检查WebDAV路径是否存在"""
        if not self._session:
            return False
        
        try:
            # 尝试获取文件信息
            await self.get_file_info(path)
            return True
        except StorageNotFoundError:
            return False
        except Exception:
            return False
    
    async def move(self, source_path: str, dest_path: str) -> bool:
        """移动/重命名WebDAV文件或目录"""
        if not self._session:
            raise StorageConnectionError("客户端未连接")
        
        try:
            # base_url = self._base_url.rstrip('/')
            # encoded_source_path = quote(source_path.strip('/'))
            # encoded_dest_path = quote(dest_path.strip('/'))
            # source_url = f"{base_url}/{encoded_source_path}"
            # dest_url = f"{base_url}/{encoded_dest_path}"
            base_url = self._base_url.rstrip('/')
            source_url = self.replace_base_path(base_url, source_path)
            dest_url = self.replace_base_path(base_url, dest_path)
            
            # WebDAV的MOVE方法
            headers = {
                'Destination': dest_url,
                'Overwrite': 'F'  # 不覆盖已存在的目标
            }
            
            async with self._session.request('MOVE', source_url, headers=headers) as response:
                if response.status in [201, 204]:  # 成功创建/移动
                    logger.info(f"移动成功: {source_path} -> {dest_path}")
                    return True
                elif response.status == 404:  # 源不存在
                    raise StorageNotFoundError(f"源路径不存在: {source_path}", source_path)
                elif response.status == 403:  # 权限不足
                    raise StoragePermissionError(f"移动权限不足: {source_path}", source_path)
                elif response.status == 412:  # 目标已存在（Overwrite: F）
                    raise StorageError("目标路径已存在")
                else:
                    error_text = await response.text()
                    raise StorageError(f"移动失败: HTTP {response.status} - {error_text}")
                    
        except Exception as e:
            # 如果已经是StorageError的子类，直接抛出
            if isinstance(e, (StorageNotFoundError, StoragePermissionError, StorageError)):
                raise
                
            error_msg = f"移动失败: {e}"
            logger.error(error_msg)
            raise StorageError(error_msg)
