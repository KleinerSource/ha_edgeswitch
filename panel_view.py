"""EdgeSwitch 面板视图。"""
import logging
import os
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class EdgeSwitchPanelView(HomeAssistantView):
    """EdgeSwitch 面板视图。"""

    url = "/edgeswitch_panel/{filename:.*}"
    name = "edgeswitch:panel"
    requires_auth = False  # 面板文件不需要认证

    def __init__(self, hass: HomeAssistant, panel_path: str) -> None:
        """初始化面板视图。"""
        self.hass = hass
        self.panel_path = panel_path

    async def get(self, request: web.Request, filename: str) -> web.Response:
        """处理面板文件请求。"""
        try:
            # 如果没有指定文件名，默认返回 index.html
            if not filename:
                filename = "index.html"
            
            # 构建文件路径
            file_path = os.path.join(self.panel_path, filename)
            
            # 检查文件是否在允许的目录内（安全检查）
            if not os.path.abspath(file_path).startswith(os.path.abspath(self.panel_path)):
                _LOGGER.warning("尝试访问面板目录外的文件: %s", file_path)
                return web.Response(
                    text="Access denied",
                    status=403,
                    headers={'Content-Type': 'text/plain; charset=utf-8'}
                )

            # 检查文件是否存在
            if not os.path.exists(file_path):
                _LOGGER.warning("面板文件不存在: %s", file_path)
                return web.Response(
                    text=f"File not found: {filename}",
                    status=404,
                    headers={'Content-Type': 'text/plain; charset=utf-8'}
                )
            
            # 读取文件内容
            with open(file_path, 'rb') as f:
                content = f.read()
            
            # 根据文件扩展名设置 Content-Type
            content_type = self._get_content_type(filename)

            # 创建响应头
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }

            # 为文本文件设置 charset
            if content_type.startswith(('text/', 'application/javascript', 'application/json')):
                headers['Content-Type'] = f"{content_type}; charset=utf-8"
            else:
                headers['Content-Type'] = content_type

            return web.Response(
                body=content,
                headers=headers
            )
            
        except Exception as e:
            _LOGGER.error("处理面板文件请求失败: %s", e)
            return web.Response(
                text=f"Internal server error: {str(e)}",
                status=500,
                content_type="text/plain"
            )

    def _get_content_type(self, filename: str) -> str:
        """根据文件扩展名获取 Content-Type。"""
        ext = os.path.splitext(filename)[1].lower()

        content_types = {
            '.html': 'text/html',
            '.css': 'text/css',
            '.js': 'application/javascript',
            '.json': 'application/json',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.ico': 'image/x-icon',
            '.woff': 'font/woff',
            '.woff2': 'font/woff2',
            '.ttf': 'font/ttf',
            '.eot': 'application/vnd.ms-fontobject',
        }

        return content_types.get(ext, 'text/plain')


class EdgeSwitchPanelRedirectView(HomeAssistantView):
    """EdgeSwitch 面板重定向视图。"""

    url = "/edgeswitch_panel"
    name = "edgeswitch:panel:redirect"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """重定向到面板主页。"""
        return web.Response(
            status=302,
            headers={'Location': '/edgeswitch_panel/index.html'}
        )


async def async_register_panel_views(hass: HomeAssistant) -> None:
    """注册面板视图。"""
    panel_path = hass.config.path("custom_components/edgeswitch/panel")
    
    # 检查面板目录是否存在
    if not os.path.exists(panel_path):
        _LOGGER.error("面板目录不存在: %s", panel_path)
        return
    
    # 注册面板文件视图
    hass.http.register_view(EdgeSwitchPanelView(hass, panel_path))
    hass.http.register_view(EdgeSwitchPanelRedirectView())
    
    _LOGGER.info("EdgeSwitch 面板视图已注册: %s", panel_path)


async def async_register_panel_to_sidebar(hass: HomeAssistant) -> bool:
    """注册面板到侧边栏。"""
    try:
        # 确保 frontend 组件已加载
        if "frontend" not in hass.config.components:
            _LOGGER.warning("Frontend 组件未加载，等待加载...")
            # 等待 frontend 组件加载
            await hass.async_add_executor_job(_wait_for_frontend, hass)

        # 方法1: 使用 hass.async_create_task 和 frontend 服务
        try:
            # 导入 frontend 组件
            from homeassistant.components import frontend

            # 注册面板
            frontend.async_register_built_in_panel(
                hass,
                "iframe",
                "EdgeSwitch",
                "mdi:switch",
                "edgeswitch",
                {"url": "/edgeswitch_panel/index.html"},
                require_admin=False,
            )
            _LOGGER.info("EdgeSwitch 面板已成功注册到侧边栏 (方法1)")
            return True

        except Exception as e1:
            _LOGGER.debug("方法1失败: %s", e1)

            # 方法2: 直接调用 frontend 组件的注册方法
            try:
                frontend_component = hass.data.get("frontend")
                if frontend_component:
                    frontend_component.async_register_built_in_panel(
                        "iframe",
                        "EdgeSwitch",
                        "mdi:switch",
                        "edgeswitch",
                        {"url": "/edgeswitch_panel/index.html"},
                        require_admin=False,
                    )
                    _LOGGER.info("EdgeSwitch 面板已成功注册到侧边栏 (方法2)")
                    return True
                else:
                    raise Exception("Frontend 组件数据不可用")

            except Exception as e2:
                _LOGGER.debug("方法2失败: %s", e2)

                # 方法3: 使用事件系统延迟注册
                try:
                    async def register_when_ready(event):
                        """当 Home Assistant 启动完成后注册面板。"""
                        try:
                            from homeassistant.components import frontend
                            frontend.async_register_built_in_panel(
                                hass,
                                "iframe",
                                "EdgeSwitch",
                                "mdi:switch",
                                "edgeswitch",
                                {"url": "/edgeswitch_panel/index.html"},
                                require_admin=False,
                            )
                            _LOGGER.info("EdgeSwitch 面板已延迟注册到侧边栏")
                        except Exception as e:
                            _LOGGER.error("延迟注册面板失败: %s", e)

                    # 监听 Home Assistant 启动完成事件
                    hass.bus.async_listen_once("homeassistant_started", register_when_ready)
                    _LOGGER.info("EdgeSwitch 面板将在 Home Assistant 启动完成后注册")
                    return True

                except Exception as e3:
                    _LOGGER.error("方法3也失败: %s", e3)

    except Exception as e:
        _LOGGER.error("注册 EdgeSwitch 面板到侧边栏时发生未预期错误: %s", e)

    # 所有方法都失败了
    _LOGGER.warning("无法将 EdgeSwitch 面板注册到侧边栏")
    _LOGGER.info("您可以通过直接访问 /edgeswitch_panel/index.html 来使用面板")
    return False


def _wait_for_frontend(hass: HomeAssistant, timeout: int = 10) -> bool:
    """等待 frontend 组件加载。"""
    import time
    start_time = time.time()

    while time.time() - start_time < timeout:
        if "frontend" in hass.config.components:
            return True
        time.sleep(0.1)

    return False
