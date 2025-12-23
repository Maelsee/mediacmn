# """
# WebDAV存储客户端实现

# 基于WebDAV协议直接实现统一的StorageClient接口，不依赖旧模块
# """

# import asyncio
# import logging
# from typing import List, Optional, Dict, Any, Iterator
# from datetime import datetime
# import aiohttp
# from urllib.parse import urljoin, urlparse, quote, unquote
# import xml.etree.ElementTree as ET

# from ..storage_client import (
#     StorageClient, StorageEntry, StorageInfo, 
#     StorageConnectionError, StorageNotFoundError, StoragePermissionError, StorageError
# )

# logger = logging.getLogger(__name__)


# class WebDAVStorageClient(StorageClient):
#     """WebDAV存储客户端"""
    
#     def __init__(self, name: str, config: Dict[str, Any]):
#         super().__init__(name, config)
#         # 获取基础配置
#         base_url = config.get('url', '').rstrip('/')
#         root_path = config.get('root_path', '').strip('/')
#         # 组合完整的 base_url
#         if root_path:
#             self._base_url = f"{base_url}/{root_path}"
#         else:
#             self._base_url = base_url

#         self._session: Optional[aiohttp.ClientSession] = None
#         self._username = config.get('username', '')
#         self._password = config.get('password', '')
#         self._timeout = config.get('timeout', 30)
#         self._verify_ssl = config.get('verify_ssl', True)
#         self._connected = False
    
#     def is_alive(self) -> bool:
#         """
#         检查 WebDAV 客户端是否依然可用。
#         这是一个同步方法，仅检查本地状态，不发起网络请求。
#         """
#         # 1. 检查逻辑连接标志
#         if not self._connected:
#             return False
            
#         # 2. 检查 aiohttp Session 状态
#         if self._session is None:
#             return False
            
#         # 3. 检查 Session 是否已被关闭
#         if self._session.closed:
#             return False
            
#         # 4. 检查底层连接池（Connector）是否还存活
#         if self._session.connector is None or self._session.connector.closed:
#             return False
            
#         return True
    
#     async def connect(self) -> bool:
#         """建立WebDAV连接"""
#         # 如果已经连接且会话有效，直接返回
#         if self._connected and self._session and not self._session.closed:
#             return True

#         # 如果存在旧会话，先关闭
#         if self._session:
#             await self._session.close()
#             self._session = None

#         try:
#             # 创建HTTP会话
#             connector = aiohttp.TCPConnector(
#                 ssl=False if not self._verify_ssl else None,
#                 limit=100,
#                 limit_per_host=30
#             )
            
#             timeout = aiohttp.ClientTimeout(total=self._timeout)
#             self._session = aiohttp.ClientSession(
#                 connector=connector,
#                 timeout=timeout,
#                 auth=aiohttp.BasicAuth(self._username, self._password) if self._username else None
#             )
            
#             # 测试连接
#             success, error = await self.check_connection()
#             if not success:
#                 # 连接失败，关闭会话
#                 await self._session.close()
#                 self._session = None
#                 raise StorageConnectionError(error or "连接测试失败")
            
#             self._connected = True
#             logger.debug(f"WebDAV存储客户端已连接: {self.name}")
#             return True
            
#         except Exception as e:
#             # 发生异常，确保会话关闭
#             if self._session:
#                 await self._session.close()
#                 self._session = None
#             self._connected = False
#             logger.error(f"WebDAV连接失败: {e}")
#             raise StorageConnectionError(f"WebDAV连接失败: {e}")
    
#     async def disconnect(self) -> None:
#         """断开WebDAV连接"""
#         self._connected = False  # 先置位，防止在关闭过程中被其他并发任务 get_client 命中
#         if self._session:
#             if not self._session.closed:
#                 await self._session.close()
#             self._session = None
#         logger.debug(f"WebDAV存储客户端已断开: {self.name}")
    
#     def _parse_webdav_response(self, xml_text: str) -> List[Dict[str, Any]]:
#         """解析WebDAV PROPFIND响应"""
#         entries = []
#         try:
#             root = ET.fromstring(xml_text)
#             # 处理命名空间
#             ns = {
#                 'd': 'DAV:',
#                 'DAV': 'DAV:'
#             }
            
#             for response in root.findall('.//d:response', ns):
#                 entry = {}
                
#                 # 获取href (路径)
#                 href_elem = response.find('d:href', ns)
#                 if href_elem is not None and href_elem.text:
#                     # URL解码处理
#                     import urllib.parse
#                     decoded_href = urllib.parse.unquote(href_elem.text)
#                     entry['path'] = urlparse(decoded_href).path
#                     entry['name'] = entry['path'].rstrip('/').split('/')[-1] or '/'
                
#                 # 获取propstat信息
#                 propstat = response.find('d:propstat', ns)
#                 if propstat is not None:
#                     prop = propstat.find('d:prop', ns)
#                     if prop is not None:
#                         # 获取资源类型
#                         resourcetype = prop.find('d:resourcetype', ns)
#                         if resourcetype is not None:
#                             entry['is_dir'] = resourcetype.find('d:collection', ns) is not None
#                         else:
#                             entry['is_dir'] = False
                        
#                         # 获取大小
#                         getcontentlength = prop.find('d:getcontentlength', ns)
#                         if getcontentlength is not None and getcontentlength.text:
#                             try:
#                                 entry['size'] = int(getcontentlength.text)
#                             except (ValueError, TypeError):
#                                 entry['size'] = 0
#                         else:
#                             entry['size'] = 0 if entry.get('is_dir') else None
                        
#                         # 获取修改时间
#                         getlastmodified = prop.find('d:getlastmodified', ns)
#                         if getlastmodified is not None and getlastmodified.text:
#                             try:
#                                 # WebDAV日期格式通常是 RFC1123
#                                 entry['modified'] = datetime.strptime(
#                                     getlastmodified.text, 
#                                     '%a, %d %b %Y %H:%M:%S %Z'
#                                 )
#                             except ValueError:
#                                 entry['modified'] = None
                        
#                         # 获取内容类型
#                         getcontenttype = prop.find('d:getcontenttype', ns)
#                         if getcontenttype is not None and getcontenttype.text:
#                             entry['content_type'] = getcontenttype.text
                        
#                         # 获取ETag
#                         getetag = prop.find('d:getetag', ns)
#                         if getetag is not None and getetag.text:
#                             entry['etag'] = getetag.text.strip('"')
                
#                 if entry:
#                     entries.append(entry)
                    
#         except ET.ParseError as e:
#             logger.warning(f"XML解析错误: {e}")
            
#         return entries

#     async def check_connection(self) -> tuple[bool, Optional[str]]:
#         """测试WebDAV连接"""
#         if not self._session:
#             return False, "HTTP会话未初始化"
        
#         try:
#             # 发送PROPFIND请求测试连接
#             url = self._base_url
#             headers = {
#                 'Depth': '0',
#                 'Content-Type': 'application/xml'
#             }
            
#             # 空的PROPFIND请求体
#             body = """<?xml version="1.0" encoding="utf-8"?>
#             <D:propfind xmlns:D="DAV:">
#             <D:prop>
#                 <D:resourcetype/>
#             </D:prop>
#             </D:propfind>"""
            
#             async with self._session.request('PROPFIND', url, headers=headers, data=body) as response:
#                 if response.status in [200, 207]:  # 207 Multi-Status 是PROPFIND的正常响应
#                     return True, None
#                 elif response.status == 401:
#                     return False, "认证失败"
#                 elif response.status == 403:
#                     return False, "权限不足"
#                 else:
#                     return False, f"连接测试失败: HTTP {response.status}"
                    
#         except Exception as e:
#             error_msg = f"连接测试异常: {e}"
#             logger.error(error_msg)
#             return False, error_msg
    
#     async def info(self, path: str = "/") -> StorageInfo:
#         """获取WebDAV系统信息"""
#         # WebDAV协议本身不直接提供空间信息，返回基础信息
#         return StorageInfo(
#             readonly=False,
#             supports_resume=True,
#             supports_range=True,
#             max_file_size=None
#         )
    
#     def replace_base_path(self, base_url: str, path: str) -> str:
#         """替换路径中的基础路径"""
#         parsed = urlparse(base_url)
#         if path.startswith(parsed.path):
#             base_url = f"{parsed.scheme}://{parsed.netloc}"
#             return f"{base_url}/{quote(path.strip('/'))}"
#         return f"{base_url}/{quote(path.strip('/'))}"

#     async def list_dir(self, path: str = "/", depth: int = 1) -> List[StorageEntry]:
#         """列出WebDAV目录内容"""
#         if not self._session:
#             raise StorageConnectionError("客户端未连接")
#         # logger.info(f'----查看输入路径: {path}')
#         try:
#             # 构建完整的URL
#             base_url = self._base_url.rstrip('/')
#             url = self.replace_base_path(base_url, path)
#             # logger.info(f'----查看URL: {url}')
#             # encoded_path = quote(path.strip('/'))
#             # url = f"{base_url}/{encoded_path}"
            
#             depth = "infinity" if depth > 1 else str(depth)
#             # 设置请求头
#             headers = {
#                 'Depth': depth,
#                 'Content-Type': 'application/xml'
#             }
            
#             # PROPFIND请求体
#             body = """<?xml version="1.0" encoding="utf-8"?>
#                 <D:propfind xmlns:D="DAV:">
#                 <D:prop>
#                     <D:displayname/>
#                     <D:getcontentlength/>
#                     <D:getlastmodified/>
#                     <D:resourcetype/>
#                     <D:getcontenttype/>
#                     <D:getetag/>
#                 </D:prop>
#                 </D:propfind>"""
                        
#             async with self._session.request('PROPFIND', url, headers=headers, data=body) as response:
#                 # logger.info(f'webdav协议文件信息响应状态: {response}')

#                 if response.status == 207:  # Multi-Status
#                     xml_content = await response.text()
#                     # logger.info(f'----查看XML内容: {xml_content}')

#                     entries = self._parse_webdav_response(xml_content)
                    
#                     # 转换为统一的StorageEntry格式
#                     storage_entries = []
#                     for entry in entries:
#                         # 跳过当前目录本身和根目录
#                         # logger.info(f'----查看结果: {entry.get('path').rstrip('/')}，输入路径: {unquote(urlparse(url).path.rstrip('/'))}')
#                         if entry.get('path').rstrip('/') == unquote(urlparse(url).path.rstrip('/')):
#                             continue
                            
#                         storage_entry = StorageEntry(
#                             name=entry.get('name', ''),
#                             path=entry.get('path', ''),
#                             is_dir=entry.get('is_dir', False),
#                             size=entry.get('size'),
#                             modified=entry.get('modified'),
#                             content_type=entry.get('content_type'),
#                             etag=entry.get('etag')
#                         )
#                         storage_entries.append(storage_entry)
                    
#                     return storage_entries
                    
#                 elif response.status == 404:
#                     raise StorageNotFoundError(f"路径不存在: {path}", path)
#                 elif response.status == 403:
#                     raise StoragePermissionError(f"权限不足: {path}", path)
#                 else:
#                     error_text = await response.text()
#                     raise StorageError(f"列出目录失败: HTTP {response.status} - {error_text}")
                    
#         except Exception as e:
#             error_msg = f"列出目录失败: {e}"
#             logger.error(error_msg)
            
#             if isinstance(e, (StorageNotFoundError, StoragePermissionError, StorageError)):
#                 raise
#             else:
#                 raise StorageError(error_msg)
    
#     async def stat(self, path: str) -> StorageEntry:
#         """获取文件/目录信息（兼容旧接口）"""
#         return await self.get_file_info(path)
    
#     async def get_file_info(self, path: str) -> StorageEntry:
#         """获取WebDAV文件/目录详细信息"""
#         if not self._session:
#             raise StorageConnectionError("客户端未连接")
        
#         try:
#             logger.info(f'获取文件信息 - 输入路径: {path}')
#             logger.info(f'基础URL: {self._base_url}')
            
#             # 使用与list_dir相同的路径处理逻辑
#             base_url = self._base_url.rstrip('/')
#             url = self.replace_base_path(base_url, path)
#             logger.info(f'修正后的URL: {url}')
            
#             # 设置请求头
#             headers = {
#                 'Depth': '0',
#                 'Content-Type': 'application/xml'
#             }
            
#             # PROPFIND请求体
#             body = """<?xml version="1.0" encoding="utf-8"?>
#             <D:propfind xmlns:D="DAV:">
#             <D:prop>
#                 <D:displayname/>
#                 <D:getcontentlength/>
#                 <D:getlastmodified/>
#                 <D:resourcetype/>
#                 <D:getcontenttype/>
#                 <D:getetag/>
#             </D:prop>
#             </D:propfind>"""
            
#             async with self._session.request('PROPFIND', url, headers=headers, data=body) as response:
#                 logger.info(f'webdav协议单文件信息响应状态: {response}')

#                 if response.status == 207:  # Multi-Status
#                     xml_content = await response.text()
#                     entries = self._parse_webdav_response(xml_content)
                    
#                     if entries:
#                         entry = entries[0]  # 只返回第一个条目
#                         return StorageEntry(
#                             name=entry.get('name', path.split('/')[-1]),
#                             path=path,
#                             is_dir=entry.get('is_dir', False),
#                             size=entry.get('size'),
#                             modified=entry.get('modified'),
#                             content_type=entry.get('content_type'),
#                             etag=entry.get('etag')
#                         )
#                     else:
#                         raise StorageNotFoundError(f"路径不存在: {path}", path)
                        
#                 elif response.status == 404:
#                     raise StorageNotFoundError(f"路径不存在: {path}", path)
#                 elif response.status == 403:
#                     raise StoragePermissionError(f"权限不足: {path}", path)
#                 else:
#                     error_text = await response.text()
#                     raise StorageError(f"获取文件信息失败: HTTP {response.status} - {error_text}")
                    
#         except Exception as e:
#             error_msg = f"获取文件信息失败: {e}"
#             logger.error(error_msg)
            
#             if isinstance(e, (StorageNotFoundError, StoragePermissionError, StorageError)):
#                 raise
#             else:
#                 raise StorageError(error_msg)
    
#     async def download_iter(self, path: str, chunk_size: int = 64 * 1024, offset: int = 0) -> Iterator[bytes]:
#         """流式下载WebDAV文件"""
#         if not self._session:
#             raise StorageConnectionError("客户端未连接")
        
#         try:
#             # 使用与get_file_info相同的路径处理逻辑
#             base_url = self._base_url.rstrip('/')
#             url = self.replace_base_path(base_url, path)
            
#             # 设置请求头，支持断点续传
#             headers = {}
#             if offset > 0:
#                 headers['Range'] = f'bytes={offset}-'
            
#             async with self._session.get(url, headers=headers) as response:
#                 if response.status == 200:
#                     async for chunk in response.content.iter_chunked(chunk_size):
#                         yield chunk
#                 elif response.status == 404:
#                     raise StorageNotFoundError(f"文件不存在: {path}", path)
#                 elif response.status == 403:
#                     raise StoragePermissionError(f"下载权限不足: {path}", path)
#                 else:
#                     error_text = await response.text()
#                     raise StorageError(f"下载失败: HTTP {response.status} - {error_text}")
                    
#         except Exception as e:
#             error_msg = f"下载文件失败: {e}"
#             logger.error(error_msg)
            
#             if isinstance(e, (StorageNotFoundError, StoragePermissionError, StorageError)):
#                 raise
#             else:
#                 raise StorageError(error_msg)
    
#     async def upload(self, path: str, data: bytes, 
#                     content_type: Optional[str] = None) -> bool:
#         """上传文件到WebDAV"""
#         if not self._session:
#             raise StorageConnectionError("客户端未连接")
        
#         try:
#             # 构建完整的URL
#             # base_url = self._base_url.rstrip('/')
#             # encoded_path = quote(path.strip('/'))
#             # url = f"{base_url}/{encoded_path}"
#             base_url = self._base_url.rstrip('/')
#             url = self.replace_base_path(base_url, path)
            
#             # 设置请求头
#             headers = {}
#             if content_type:
#                 headers['Content-Type'] = content_type
            
#             async with self._session.put(url, data=data, headers=headers) as response:
#                 if response.status in [200, 201, 204]:  # 成功创建/更新
#                     logger.info(f"文件上传成功: {path}")
#                     return True
#                 elif response.status == 405:  # Method Not Allowed，文件已存在或其他限制
#                     error_text = await response.text()
#                     logger.warning(f"WebDAV上传返回405，尝试其他方法或文件已存在: {path} - {error_text}")
#                     # 某些WebDAV服务器对PUT方法有限制，尝试检查文件是否存在
#                     try:
#                         if await self.exists(path):
#                             logger.info(f"文件已存在，视为上传成功: {path}")
#                             return True
#                         else:
#                             # 文件不存在但405，可能是服务器配置问题
#                             logger.error(f"WebDAV服务器配置不支持PUT上传: {path}")
#                             return False
#                     except Exception as exist_check_error:
#                         logger.warning(f"存在性检查失败，保守返回失败: {exist_check_error}")
#                         return False
#                 elif response.status == 403:
#                     raise StoragePermissionError(f"上传权限不足: {path}", path)
#                 else:
#                     error_text = await response.text()
#                     raise StorageError(f"上传失败: HTTP {response.status} - {error_text}")
                    
#         except Exception as e:
#             error_msg = f"上传文件失败: {e}"
#             logger.error(error_msg)
            
#             if isinstance(e, (StoragePermissionError, StorageError)):
#                 raise
#             else:
#                 raise StorageError(error_msg)
    
#     async def create_dir(self, path: str) -> bool:
#         """在WebDAV中创建目录"""
#         if not self._session:
#             raise StorageConnectionError("客户端未连接")
        
#         try:
#             # 构建完整的URL
#             # base_url = self._base_url.rstrip('/')
#             # encoded_path = quote(path.strip('/'))
#             # url = f"{base_url}/{encoded_path}"
#             base_url = self._base_url.rstrip('/')
#             url = self.replace_base_path(base_url, path)
            
#             # WebDAV的MKCOL方法创建目录
#             async with self._session.request('MKCOL', url) as response:
#                 if response.status == 201:  # 成功创建
#                     logger.info(f"目录创建成功: {path}")
#                     return True
#                 elif response.status == 405:  # Method Not Allowed，目录已存在
#                     logger.info(f"目录已存在: {path}")
#                     return True  # 视为成功
#                 elif response.status == 403:
#                     raise StoragePermissionError(f"创建目录权限不足: {path}", path)
#                 elif response.status == 409:  # Conflict，父目录不存在
#                     raise StorageError(f"父目录不存在: {path}")
#                 else:
#                     error_text = await response.text()
#                     raise StorageError(f"创建目录失败: HTTP {response.status} - {error_text}")
                    
#         except Exception as e:
#             error_msg = f"创建目录失败: {e}"
#             logger.error(error_msg)
            
#             if isinstance(e, (StoragePermissionError, StorageError)):
#                 raise
#             else:
#                 raise StorageError(error_msg)
    
#     async def delete(self, path: str) -> bool:
#         """删除WebDAV文件或目录"""
#         if not self._session:
#             raise StorageConnectionError("客户端未连接")
        
#         try:
#             # WebDAV的DELETE方法
#             if not self._session:
#                 raise StorageConnectionError("HTTP会话未初始化")
            
#             # url = urljoin(self._base_url, path.lstrip('/'))
#             # 构建完整的URL
#             # base_url = self._base_url.rstrip('/')
#             # encoded_path = quote(path.strip('/'))
#             # url = f"{base_url}/{encoded_path}"
#             base_url = self._base_url.rstrip('/')
#             url = self.replace_base_path(base_url, path)
            
#             async with self._session.delete(url) as response:
#                 if response.status in [200, 204]:  # 成功删除
#                     logger.info(f"删除成功: {path}")
#                     return True
#                 elif response.status == 404:  # 不存在
#                     raise StorageNotFoundError(f"路径不存在: {path}", path)
#                 elif response.status == 403:  # 权限不足
#                     raise StoragePermissionError(f"删除权限不足: {path}", path)
#                 else:
#                     error_text = await response.text()
#                     raise StorageError(f"删除失败: {response.status} - {error_text}")
                    
#         except Exception as e:
#             # 如果已经是StorageError的子类，直接抛出
#             if isinstance(e, (StorageNotFoundError, StoragePermissionError, StorageError)):
#                 raise
            
#             error_msg = f"删除失败: {e}"
#             logger.error(error_msg)
#             raise StorageError(error_msg)
    
#     async def exists(self, path: str) -> bool:
#         """检查WebDAV路径是否存在"""
#         if not self._session:
#             return False
        
#         try:
#             # 尝试获取文件信息
#             await self.get_file_info(path)
#             return True
#         except StorageNotFoundError:
#             return False
#         except Exception:
#             return False
    
#     async def move(self, source_path: str, dest_path: str) -> bool:
#         """移动/重命名WebDAV文件或目录"""
#         if not self._session:
#             raise StorageConnectionError("客户端未连接")
        
#         try:
#             # base_url = self._base_url.rstrip('/')
#             # encoded_source_path = quote(source_path.strip('/'))
#             # encoded_dest_path = quote(dest_path.strip('/'))
#             # source_url = f"{base_url}/{encoded_source_path}"
#             # dest_url = f"{base_url}/{encoded_dest_path}"
#             base_url = self._base_url.rstrip('/')
#             source_url = self.replace_base_path(base_url, source_path)
#             dest_url = self.replace_base_path(base_url, dest_path)
            
#             # WebDAV的MOVE方法
#             headers = {
#                 'Destination': dest_url,
#                 'Overwrite': 'F'  # 不覆盖已存在的目标
#             }
            
#             async with self._session.request('MOVE', source_url, headers=headers) as response:
#                 if response.status in [201, 204]:  # 成功创建/移动
#                     logger.info(f"移动成功: {source_path} -> {dest_path}")
#                     return True
#                 elif response.status == 404:  # 源不存在
#                     raise StorageNotFoundError(f"源路径不存在: {source_path}", source_path)
#                 elif response.status == 403:  # 权限不足
#                     raise StoragePermissionError(f"移动权限不足: {source_path}", source_path)
#                 elif response.status == 412:  # 目标已存在（Overwrite: F）
#                     raise StorageError("目标路径已存在")
#                 else:
#                     error_text = await response.text()
#                     raise StorageError(f"移动失败: HTTP {response.status} - {error_text}")
                    
#         except Exception as e:
#             # 如果已经是StorageError的子类，直接抛出
#             if isinstance(e, (StorageNotFoundError, StoragePermissionError, StorageError)):
#                 raise
                
#             error_msg = f"移动失败: {e}"
#             logger.error(error_msg)
#             raise StorageError(error_msg)


import asyncio
import logging
from typing import List, Optional, Dict, Any, AsyncIterator
from datetime import datetime
import aiohttp
from urllib.parse import urlparse, quote, unquote
from lxml import etree  # 需要安装 lxml: pip install lxml

from ..storage_client import (
    StorageClient, StorageEntry, StorageInfo, 
    StorageConnectionError, StorageNotFoundError, StorageError
)

logger = logging.getLogger(__name__)

class WebDAVStorageClient(StorageClient):
    """优化后的 WebDAV 存储客户端"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        # 基础配置
        base_url = config.get('url', '').rstrip('/')
        root_path = config.get('root_path', '').strip('/')
        # self._base_url = f"{base_url}/{root_path}" if root_path else base_url
        self._base_url = f"{base_url}/"
        self._root_path =  f"{root_path}" if root_path else ""
        
        self._username = config.get('username', '')
        self._password = config.get('password', '')
        self._timeout_val = config.get('timeout', 30)
        self._verify_ssl = config.get('verify_ssl', True)
        
        # 优化点 1 & 4: 并发与 Session 管理
        self._session: Optional[aiohttp.ClientSession] = None
        self._max_concurrency = config.get('max_concurrency', 5)  # 显式保存最大并发数
        # 2. 用保存的最大并发数初始化信号量
        self._semaphore = asyncio.Semaphore(self._max_concurrency)
        self._connected = False
        # 新增：内部异步锁，保护 Session 初始化和关闭
        self._lock = asyncio.Lock()
        # 命名空间映射 (WebDAV 标准)
        self._ns = {'d': 'DAV:'}
    
    def get_max_concurrency(self) -> int:
        """获取最大并发数"""
        return self._max_concurrency
    
    def is_alive(self) -> bool:
        """
        检查 WebDAV 客户端是否依然可用。
        这是一个同步方法，仅检查本地状态，不发起网络请求。
        """
        return bool(self._connected and self._session and not self._session.closed)
    
    # async def _ensure_session(self):
    #     """延迟初始化并确保 Session 有效"""
    #     """线程安全的 Session 初始化"""
    #     if self._session is not None and not self._session.closed:
    #         return

    #     async with self._lock:
    #         # 双重检查锁
    #         if self._session is None or self._session.closed:
    #             connector = aiohttp.TCPConnector(
    #                 ssl=None if self._verify_ssl else False,
    #                 limit=100,
    #                 keepalive_timeout=30
    #             )
    #             self._session = aiohttp.ClientSession(
    #                 connector=connector,
    #                 auth=aiohttp.BasicAuth(self._username, self._password) if self._username else None,
    #                 timeout=aiohttp.ClientTimeout(total=self._timeout_val)
    #             )
    
    async def connect(self) -> bool:
        """建立 WebDAV 连接"""
        try:
            await self._ensure_session()
            success, error = await self.check_connection()
            if not success:
                if self._session:
                    if not self._session.closed:
                        await self._session.close()
                    self._session = None
                raise StorageConnectionError(error or "连接测试失败")
            self._connected = True
            return True
        except Exception as e:
            await self.disconnect()
            raise StorageConnectionError(f"WebDAV 连接失败: {str(e)}")
    
    async def _ensure_session(self):
        """线程安全的 Session 初始化，优化了连接回收"""
        if self._session is not None and not self._session.closed:
            return

        async with self._lock:
            if self._session is None or self._session.closed:
                # 优化：限制底层连接池，防止单个 Client 占用过多系统句柄
                connector = aiohttp.TCPConnector(
                    ssl=None if self._verify_ssl else False,
                    limit=self._max_concurrency,  # 限制这个 Client 自己的连接池大小
                    keepalive_timeout=15,         # 缩短保持时间，加速任务后的资源回收
                    force_close=False             # 扫描期间允许复用，但关闭时会由 session.close 处理
                )
                
                self._session = aiohttp.ClientSession(
                    connector=connector,
                    auth=aiohttp.BasicAuth(self._username, self._password) if self._username else None,
                    # 显式设置超时，防止挂死
                    timeout=aiohttp.ClientTimeout(total=self._timeout_val, connect=10)
                )

    async def disconnect(self) -> None:
        """安全断开并确保清理"""
        # 如果有正在进行的 IO，这里需要配合信号量或 cancel
        async with self._lock:
            if self._session:
                # aiohttp 官方推荐：在某些情况下给底层连接一点点‘喘息’时间
                # 但在你的任务模式下，直接 close 是最安全的
                if not self._session.closed:
                    await self._session.close()
                
                # 彻底释放
                self._session = None
                
            self._connected = False
            # logger.debug(f"WebDAV 客户端 {self.name} 资源已彻底释放")
    
    # 优化点 3 & 4: 统一请求入口与异常重试
    async def _request(self, method: str, url: str, retries: int = 3, **kwargs) -> aiohttp.ClientResponse:
        """
        带有并发控制和自动重试的统一请求入口
        """
        await self._ensure_session()
        
        last_exception = None
        for attempt in range(retries):
            try:
                async with self._semaphore:
                    # 注意：返回 response 对象时，不能直接退出 async with session.request 作用域
                    # 我们在这里让调用者通过上下文管理器处理 response
                    response = await self._session.request(method, url, **kwargs)
                    
                    # 针对 WebDAV 常见的网络抖动或 5xx 错误进行重试
                    if response.status >= 500 and attempt < retries - 1:
                        logger.warning(f"WebDAV 远程服务器错误 {response.status}, 正在重试 ({attempt + 1}/{retries})")
                        await asyncio.sleep(1 * (attempt + 1)) # 指数退避
                        continue
                        
                    return response
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e
                if attempt < retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                logger.error(f"WebDAV 请求失败 {method} {url}: {str(e)}")
                raise StorageError(f"网络请求失败: {str(last_exception)}")
        
        raise StorageError(f"请求在 {retries} 次重试后仍然失败")

    # 优化点 2: 使用 lxml 提升解析性能
    def _parse_webdav_response(self, xml_bytes: bytes, current_request_path: str, skip_self: bool = True) -> List[Dict[str, Any]]:
        """使用 lxml 高效解析 XML"""
        entries = []
        # 统一规范化对比路径：去除末尾斜杠
        target_path = unquote(current_request_path.rstrip('/'))
        # logger.info(f'----解析目标路径: {target_path}')
        try:
            parser = etree.XMLParser(recover=True, encoding='utf-8')
            root = etree.fromstring(xml_bytes, parser=parser)
            
            # 使用 XPath 快速定位所有 response 节点
            responses = root.xpath('.//d:response', namespaces=self._ns)
            
            for resp in responses:
                entry = {}
                href = resp.xpath('d:href/text()', namespaces=self._ns)
                if not href: continue
                
                # decoded_path = unquote(href[0])
                # 1. 解析并规范化路径
                decoded_path = unquote(href[0])
                full_path = urlparse(decoded_path).path
                normalized_entry_path = full_path.rstrip('/')
                
                # 2. 核心过滤：如果解析出的路径与请求路径一致，直接跳过，不放入 entries
                if skip_self and normalized_entry_path == target_path:
                    logger.debug(f'----匹配结果中跳过当前请求路径: {normalized_entry_path}=={target_path}')
                    continue
                entry['path'] = urlparse(decoded_path).path
                entry['name'] = entry['path'].rstrip('/').split('/')[-1] or '/'

                # 获取属性
                prop = resp.xpath('.//d:prop', namespaces=self._ns)[0]
                
                # 是否为目录
                resourcetype = prop.xpath('d:resourcetype', namespaces=self._ns)[0]
                entry['is_dir'] = len(resourcetype.xpath('d:collection', namespaces=self._ns)) > 0
                
                # 文件大小
                size_str = prop.xpath('d:getcontentlength/text()', namespaces=self._ns)
                entry['size'] = int(size_str[0]) if size_str else (0 if entry['is_dir'] else None)
                
                # 修改时间
                mod_str = prop.xpath('d:getlastmodified/text()', namespaces=self._ns)
                if mod_str:
                    try:
                        # 兼容 RFC1123 格式
                        entry['modified'] = datetime.strptime(mod_str[0], '%a, %d %b %Y %H:%M:%S %Z')
                    except ValueError:
                        entry['modified'] = None
                
                entries.append(entry)
        except Exception as e:
            logger.error(f"LXML 解析 WebDAV 响应失败: {e}")
        return entries

    def _build_url(self, path: str) -> str:
        """统一路径构建，处理斜杠和转义"""
        clean_path = path.strip('/')
        # 保持 root_path 逻辑
        url = f"{self._base_url}{quote(clean_path)}/"
        return url

    async def list_dir(self, path: str = "/", depth: int = 1) -> List[StorageEntry]:
        """列出目录"""
        url = self._build_url(path)
        # if not url.endswith('/'): url += '/'
        logger.info(f'---扫描目录: {path}')
        logger.debug(f'----查看url: {url}')
        headers = {
            'Depth': 'infinity' if depth > 1 else str(depth),
            # 'Depth': "1",
            'Content-Type': 'application/xml; charset="utf-8"'
        }
        body = """<?xml version="1.0" encoding="utf-8"?><D:propfind xmlns:D="DAV:"><D:prop>
                    <D:displayname/><D:getcontentlength/><D:getlastmodified/><D:resourcetype/><D:getetag/>
                </D:prop></D:propfind>"""

        async with await self._request('PROPFIND', url, headers=headers, data=body) as resp:
            if resp.status == 207:
                content = await resp.read() # 读取字节流给 lxml
                parsed_entries = self._parse_webdav_response(content, urlparse(url).path)
                logger.debug(f'----查看解析结果: {parsed_entries}')
                
                storage_entries = []
                # # 排除自身路径
                # current_url_path = unquote(urlparse(url).path.rstrip('/'))
                # logger.info(f'----查看当前URL路径: {current_url_path}')
                
                for item in parsed_entries:
                    # if item['path'].rstrip('/') == current_url_path:
                    #     logger.info(f'----跳过当前路径: {item["path"].rstrip("/")}')
                    #     continue
                    storage_entries.append(StorageEntry(**item))
                return storage_entries
            elif resp.status == 404:
                raise StorageNotFoundError(f"路径不存在: {path}", path)
            else:
                raise StorageError(f"HTTP {resp.status}: {await resp.text()}")

    async def download_iter(self, path: str, chunk_size: int = 128 * 1024, offset: int = 0) -> AsyncIterator[bytes]:
        """流式下载"""
        url = self._build_url(path)
        headers = {'Range': f'bytes={offset}-'} if offset > 0 else {}
        
        # 注意：下载大文件时不应在 _request 内部 await resp.read()
        # 我们直接手动处理信号量和请求以支持流式
        await self._ensure_session()
        async with self._semaphore:
            async with self._session.get(url, headers=headers) as resp:
                if resp.status in [200, 206]:
                    async for chunk in resp.content.iter_chunked(chunk_size):
                        yield chunk
                elif resp.status == 404:
                    raise StorageNotFoundError(path)
                else:
                    raise StorageError(f"下载失败: {resp.status}")

    async def upload(self, path: str, data: bytes, content_type: Optional[str] = None) -> bool:
        """上传"""
        url = self._build_url(path)
        headers = {'Content-Type': content_type} if content_type else {}
        async with await self._request('PUT', url, data=data, headers=headers) as resp:
            if resp.status in [200, 201, 204]:
                return True
            raise StorageError(f"上传失败: {resp.status}")

    async def exists(self, path: str) -> bool:
        """检查是否存在"""
        url = self._build_url(path)
        headers = {'Depth': '0'}
        try:
            async with await self._request('PROPFIND', url, headers=headers) as resp:
                return resp.status in [200, 207]
        except:
            return False

    async def check_connection(self) -> tuple[bool, Optional[str]]:
        """测试连接"""
        try:
            url = self._base_url+self._root_path+'/'
            headers = {'Depth': '0'}
            async with await self._request('PROPFIND', url, headers=headers) as resp:
                if resp.status in [200, 207]:
                    logger.info("WebDAV 连接测试成功")
                    return True, None
                return False, f"HTTP {resp.status}"
        except Exception as e:
            return False, str(e)
    # 1. 实现 info 方法
    async def info(self, path: str = "/") -> StorageInfo:
        """获取 WebDAV 存储系统信息"""
        # WebDAV 协议通常不通过标准接口返回剩余空间，返回通用能力支持情况
        return StorageInfo(
            readonly=False,
            supports_resume=True,
            supports_range=True,
            max_file_size=None
        )

    # 2. 实现 get_file_info 方法
    async def get_file_info(self, path: str) -> StorageEntry:
        """获取单个文件或目录的详细信息"""
        url = self._build_url(path)
        headers = {'Depth': '0', 'Content-Type': 'application/xml; charset="utf-8"'}
        
        async with await self._request('PROPFIND', url, headers=headers) as resp:
            if resp.status == 207:
                content = await resp.read()
                parsed_entries = self._parse_webdav_response(content, urlparse(url).path, skip_self=False)
                if parsed_entries:
                    # 即使返回多个，Depth 0 保证第一个就是请求的路径本身
                    return StorageEntry(**parsed_entries[0])
                raise StorageNotFoundError(f"解析响应失败: {path}", path)
            elif resp.status == 404:
                raise StorageNotFoundError(f"路径不存在: {path}", path)
            else:
                raise StorageError(f"获取信息失败 HTTP {resp.status}")

    # 3. 实现 stat 方法 (通常与 get_file_info 逻辑一致)
    async def stat(self, path: str) -> StorageEntry:
        """兼容性接口，调用 get_file_info"""
        return await self.get_file_info(path)

    # 4. 实现 create_dir 方法
    async def create_dir(self, path: str) -> bool:
        """创建目录"""
        url = self._build_url(path)
        # WebDAV 使用 MKCOL 创建目录
        async with await self._request('MKCOL', url) as resp:
            if resp.status == 201:
                return True
            elif resp.status == 405: # 目录已存在
                return True
            elif resp.status == 409: # 中间目录不存在
                raise StorageError(f"父目录不存在，无法创建: {path}")
            else:
                raise StorageError(f"创建目录失败: HTTP {resp.status}")

    # 5. 实现 delete 方法
    async def delete(self, path: str) -> bool:
        """删除文件或目录"""
        url = self._build_url(path)
        async with await self._request('DELETE', url) as resp:
            if resp.status in [200, 204]:
                return True
            elif resp.status == 404:
                raise StorageNotFoundError(f"要删除的路径不存在: {path}", path)
            else:
                raise StorageError(f"删除失败: HTTP {resp.status}")

    # 6. 实现 move 方法
    async def move(self, source_path: str, dest_path: str) -> bool:
        """移动或重命名"""
        source_url = self._build_url(source_path)
        dest_url = self._build_url(dest_path)
        
        headers = {
            'Destination': dest_url,
            'Overwrite': 'F'  # 不覆盖目标文件
        }
        
        async with await self._request('MOVE', source_url, headers=headers) as resp:
            if resp.status in [201, 204]:
                return True
            elif resp.status == 412: # Overwrite 为 F 且目标已存在时返回 412
                raise StorageError(f"目标路径已存在: {dest_path}")
            elif resp.status == 404:
                raise StorageNotFoundError(f"源路径不存在: {source_path}", source_path)
            else:
                raise StorageError(f"移动失败: HTTP {resp.status}")