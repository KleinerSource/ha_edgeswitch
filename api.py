"""EdgeSwitch API 客户端，用于与 Ubiquiti UniFi 交换机通信。"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp
from aiohttp import ClientError, ClientTimeout

from .const import (
    API_DEVICE_ENDPOINT,
    API_INTERFACES_ENDPOINT,
    API_LOGIN_ENDPOINT,
    API_LOGOUT_ENDPOINT,
    API_STATISTICS_ENDPOINT,
    DEFAULT_TIMEOUT,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_INVALID_URL,
    ERROR_TIMEOUT,
    ERROR_UNKNOWN,
)

_LOGGER = logging.getLogger(__name__)


class EdgeSwitchAPIError(Exception):
    """EdgeSwitch API 错误基类。"""


class EdgeSwitchConnectionError(EdgeSwitchAPIError):
    """连接错误。"""


class EdgeSwitchAuthError(EdgeSwitchAPIError):
    """认证错误。"""


class EdgeSwitchAPI:
    """EdgeSwitch API 客户端。"""

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        verify_ssl: bool = True,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """初始化 API 客户端。
        
        Args:
            url: 交换机的 URL（例如：https://10.0.0.254）
            username: 登录用户名
            password: 登录密码
            verify_ssl: 是否验证 SSL 证书
            timeout: 请求超时时间（秒）
        """
        self.url = self._normalize_url(url)
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._session: aiohttp.ClientSession | None = None
        self._logged_in = False
        self._auth_token: str | None = None

    def _normalize_url(self, url: str) -> str:
        """标准化 URL 格式。"""
        if not url:
            raise ValueError("URL 不能为空")

        # 如果没有协议前缀，添加 https://
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # 验证 URL 格式
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                raise ValueError("无效的 URL 格式")

            # 检查主机名是否有效（至少包含一个点或者是 IP 地址）
            hostname = parsed.netloc.split(':')[0]  # 移除端口号
            if not hostname:
                raise ValueError("无效的主机名")

            # 简单的主机名验证：应该包含点或者是有效的 IP 地址格式
            if not ('.' in hostname or hostname.replace('.', '').isdigit()):
                # 检查是否是简单的单词（如 "invalid_url"）
                if hostname.isalpha() or '_' in hostname:
                    raise ValueError("无效的主机名格式")

        except ValueError:
            raise
        except Exception as err:
            raise ValueError(f"无效的 URL: {err}") from err

        # 移除末尾的斜杠
        return url.rstrip("/")

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP 会话。"""
        if self._session is None or self._session.closed:
            # 配置 SSL 连接器
            if self.verify_ssl:
                connector = aiohttp.TCPConnector(ssl=True)
            else:
                connector = aiohttp.TCPConnector(ssl=False)

            timeout = ClientTimeout(total=self.timeout)
            # 设置基础头部，包含 Referer
            base_headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "Referer": f"{self.url}/",
                "User-Agent": "Home Assistant EdgeSwitch Integration"
            }
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=base_headers
            )
        return self._session

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """发送 HTTP 请求。"""
        session = await self._get_session()
        url = urljoin(self.url, endpoint)
        
        try:
            _LOGGER.debug("发送 %s 请求到: %s", method, url)
            if data:
                _LOGGER.debug("请求数据: %s", data)

            # 准备请求参数
            request_kwargs = {"method": method, "url": url}

            # 准备请求头
            headers = {}

            # 如果已登录，添加认证 token
            if self._logged_in and self._auth_token:
                headers["x-auth-token"] = self._auth_token

            if data is not None:
                # 手动序列化 JSON 以确保正确的 Content-Length
                json_data = json.dumps(data, ensure_ascii=False)
                request_kwargs["data"] = json_data.encode('utf-8')
                # 设置 Content-Type 和 Content-Length
                headers.update({
                    "Content-Type": "application/json;charset=UTF-8",
                    "Content-Length": str(len(json_data.encode('utf-8')))
                })

            if headers:
                request_kwargs["headers"] = headers

            async with session.request(**request_kwargs) as response:
                response_text = await response.text()
                _LOGGER.debug("响应状态: %s, 内容: %s", response.status, response_text)
                
                if response.content_type == "application/json":
                    response_data = await response.json()
                else:
                    # 尝试解析为 JSON
                    try:
                        response_data = json.loads(response_text)
                    except json.JSONDecodeError:
                        response_data = {"message": response_text}
                
                # EdgeSwitch 可能返回 HTTP 200 但在 JSON 中包含错误信息
                # 检查 JSON 响应中的状态
                if isinstance(response_data, dict):
                    # 检查 EdgeSwitch 特定的错误格式
                    status_code = response_data.get("statusCode")
                    error_code = response_data.get("error")

                    if status_code == 200 and error_code == 0:
                        # 成功响应
                        return response_data
                    elif status_code is not None and status_code != 200:
                        # EdgeSwitch 返回的错误
                        error_msg = response_data.get("detail", response_data.get("message", f"EdgeSwitch error {status_code}"))
                        if status_code == 401 or status_code == 403:
                            raise EdgeSwitchAuthError(f"认证失败: {error_msg}")
                        else:
                            raise EdgeSwitchAPIError(f"API 错误: {error_msg}")

                # 检查 HTTP 状态码
                if response.status >= 400:
                    error_msg = response_data.get("message", f"HTTP {response.status}")
                    if response.status == 401:
                        raise EdgeSwitchAuthError(f"认证失败: {error_msg}")
                    else:
                        raise EdgeSwitchConnectionError(f"请求失败: {error_msg}")

                return response_data

        except (EdgeSwitchAuthError, EdgeSwitchConnectionError):
            raise
        except asyncio.TimeoutError as err:
            raise EdgeSwitchConnectionError("请求超时") from err
        except ClientError as err:
            # 提供更详细的连接错误信息
            error_msg = str(err)
            if "Cannot connect to host" in error_msg:
                if "ssl" in error_msg.lower():
                    raise EdgeSwitchConnectionError(
                        f"SSL 连接失败: {err}. 请检查 URL 是否正确，或尝试禁用 SSL 验证"
                    ) from err
                else:
                    raise EdgeSwitchConnectionError(
                        f"无法连接到设备: {err}. 请检查 URL 和网络连接"
                    ) from err
            else:
                raise EdgeSwitchConnectionError(f"连接错误: {err}") from err
        except Exception as err:
            _LOGGER.exception("请求过程中发生未知错误")
            raise EdgeSwitchAPIError(f"未知错误: {err}") from err

    async def login(self) -> bool:
        """登录到 EdgeSwitch。
        
        Returns:
            True 如果登录成功
            
        Raises:
            EdgeSwitchAuthError: 认证失败
            EdgeSwitchConnectionError: 连接失败
        """
        if self._logged_in:
            return True
        
        login_data = {
            "username": self.username,
            "password": self.password,
        }
        
        try:
            # 登录请求需要特殊处理，因为需要从响应头获取 token
            session = await self._get_session()

            # 准备登录请求
            json_data = json.dumps(login_data, ensure_ascii=False)
            headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "Referer": f"{self.url}/",
                "Content-Length": str(len(json_data.encode('utf-8')))
            }

            async with session.post(
                f"{self.url}{API_LOGIN_ENDPOINT}",
                data=json_data.encode('utf-8'),
                headers=headers
            ) as response:

                # 获取响应内容
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text)
                except json.JSONDecodeError:
                    response_data = {"message": response_text}

                # 检查登录是否成功
                if response.status == 200 and response_data.get("statusCode") == 200 and response_data.get("error") == 0:
                    # 从响应头获取认证 token
                    auth_token = response.headers.get('x-auth-token')
                    if auth_token:
                        self._auth_token = auth_token
                        self._logged_in = True
                        _LOGGER.info("成功登录到 EdgeSwitch: %s，获得认证 token", self.url)
                        return True
                    else:
                        raise EdgeSwitchAuthError("登录成功但未获得认证 token")
                else:
                    error_msg = response_data.get("detail", f"HTTP {response.status}")
                    raise EdgeSwitchAuthError(f"登录失败: {error_msg}")
                
        except (EdgeSwitchAuthError, EdgeSwitchConnectionError):
            raise
        except Exception as err:
            raise EdgeSwitchAPIError(f"登录过程中发生错误: {err}") from err

    async def logout(self) -> None:
        """从 EdgeSwitch 登出。"""
        if not self._logged_in:
            return

        try:
            await self._make_request("POST", API_LOGOUT_ENDPOINT)
            _LOGGER.info("成功从 EdgeSwitch 登出")
        except Exception as err:
            _LOGGER.warning("登出时发生错误: %s", err)
        finally:
            self._logged_in = False
            self._auth_token = None
            if self._session and not self._session.closed:
                await self._session.close()

    async def test_connection(self) -> dict[str, Any]:
        """测试连接并返回结果。
        
        Returns:
            包含测试结果的字典，格式：
            {
                "success": bool,
                "error": str | None,
                "error_code": str | None
            }
        """
        try:
            await self.login()
            await self.logout()
            return {"success": True, "error": None, "error_code": None}
        except EdgeSwitchAuthError as err:
            return {
                "success": False,
                "error": str(err),
                "error_code": ERROR_INVALID_AUTH
            }
        except EdgeSwitchConnectionError as err:
            if "timeout" in str(err).lower():
                error_code = ERROR_TIMEOUT
            else:
                error_code = ERROR_CANNOT_CONNECT
            return {
                "success": False,
                "error": str(err),
                "error_code": error_code
            }
        except ValueError as err:
            return {
                "success": False,
                "error": str(err),
                "error_code": ERROR_INVALID_URL
            }
        except Exception as err:
            return {
                "success": False,
                "error": str(err),
                "error_code": ERROR_UNKNOWN
            }

    def is_logged_in(self) -> bool:
        """检查是否已登录。"""
        return self._logged_in

    async def get_device_info(self) -> dict[str, Any]:
        """获取设备信息。

        Returns:
            包含设备信息的字典

        Raises:
            EdgeSwitchAuthError: 未登录或认证失败
            EdgeSwitchConnectionError: 连接失败
            EdgeSwitchAPIError: 其他 API 错误
        """
        if not self._logged_in:
            raise EdgeSwitchAuthError("必须先登录才能获取设备信息")

        try:
            response = await self._make_request("GET", API_DEVICE_ENDPOINT)
            _LOGGER.debug("获取设备信息成功")
            return response
        except (EdgeSwitchAuthError, EdgeSwitchConnectionError):
            raise
        except Exception as err:
            raise EdgeSwitchAPIError(f"获取设备信息失败: {err}") from err

    async def get_statistics(self) -> list[dict[str, Any]]:
        """获取统计信息。

        Returns:
            包含统计信息的列表

        Raises:
            EdgeSwitchAuthError: 未登录或认证失败
            EdgeSwitchConnectionError: 连接失败
            EdgeSwitchAPIError: 其他 API 错误
        """
        if not self._logged_in:
            raise EdgeSwitchAuthError("必须先登录才能获取统计信息")

        try:
            response = await self._make_request("GET", API_STATISTICS_ENDPOINT)
            _LOGGER.debug("获取统计信息成功")

            # 确保返回的是列表格式
            if isinstance(response, list):
                return response
            else:
                # 如果不是列表，包装成列表
                return [response]
        except (EdgeSwitchAuthError, EdgeSwitchConnectionError):
            raise
        except Exception as err:
            raise EdgeSwitchAPIError(f"获取统计信息失败: {err}") from err

    async def get_interfaces(self) -> list[dict[str, Any]]:
        """获取接口配置信息。

        Returns:
            包含接口配置信息的列表

        Raises:
            EdgeSwitchAuthError: 未登录或认证失败
            EdgeSwitchConnectionError: 连接失败
            EdgeSwitchAPIError: 其他 API 错误
        """
        if not self._logged_in:
            raise EdgeSwitchAuthError("必须先登录才能获取接口配置信息")

        try:
            response = await self._make_request("GET", API_INTERFACES_ENDPOINT)
            _LOGGER.debug("获取接口配置信息成功")

            # 确保返回的是列表格式
            if isinstance(response, list):
                return response
            else:
                # 如果不是列表，包装成列表
                return [response]
        except (EdgeSwitchAuthError, EdgeSwitchConnectionError):
            raise
        except Exception as err:
            raise EdgeSwitchAPIError(f"获取接口配置信息失败: {err}") from err

    async def close(self) -> None:
        """关闭 API 客户端。"""
        await self.logout()
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        self._logged_in = False
        self._auth_token = None
