"""EdgeSwitch 面板注册模块 - Home Assistant 2025.8 兼容版本。"""
import logging
from typing import Any, Dict

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change

_LOGGER = logging.getLogger(__name__)


class EdgeSwitchPanelRegistration:
    """EdgeSwitch 面板注册管理器。"""

    def __init__(self, hass: HomeAssistant) -> None:
        """初始化面板注册管理器。"""
        self.hass = hass
        self.registered = False
        self.registration_attempts = 0
        self.max_attempts = 5

    async def async_register_panel(self) -> bool:
        """异步注册面板到侧边栏。"""
        if self.registered:
            _LOGGER.debug("EdgeSwitch 面板已经注册")
            return True

        self.registration_attempts += 1
        _LOGGER.info("尝试注册 EdgeSwitch 面板 (第 %d 次)", self.registration_attempts)

        # 方法1: 使用标准的 frontend 组件注册
        if await self._try_standard_registration():
            return True

        # 方法2: 使用直接导入方式
        if await self._try_direct_import_registration():
            return True

        # 方法3: 使用事件监听延迟注册
        if await self._try_event_based_registration():
            return True

        # 方法4: 使用手动面板数据注册
        if await self._try_manual_registration():
            return True

        _LOGGER.error("所有面板注册方法都失败了")
        return False

    async def _try_standard_registration(self) -> bool:
        """尝试标准的面板注册方法。"""
        try:
            # 检查 frontend 组件是否可用
            if hasattr(self.hass, 'components') and hasattr(self.hass.components, 'frontend'):
                self.hass.components.frontend.async_register_built_in_panel(
                    "iframe",
                    "EdgeSwitch",
                    "mdi:switch",
                    "edgeswitch",
                    {"url": "/edgeswitch_panel/index.html"},
                    require_admin=False,
                )
                self.registered = True
                _LOGGER.info("EdgeSwitch 面板已通过标准方法注册")
                return True
        except Exception as e:
            _LOGGER.debug("标准注册方法失败: %s", e)
        
        return False

    async def _try_direct_import_registration(self) -> bool:
        """尝试直接导入 frontend 组件进行注册。"""
        try:
            from homeassistant.components import frontend
            
            # 检查 frontend 模块是否有注册方法
            if hasattr(frontend, 'async_register_built_in_panel'):
                frontend.async_register_built_in_panel(
                    self.hass,
                    "iframe",
                    "EdgeSwitch",
                    "mdi:switch",
                    "edgeswitch",
                    {"url": "/edgeswitch_panel/index.html"},
                    require_admin=False,
                )
                self.registered = True
                _LOGGER.info("EdgeSwitch 面板已通过直接导入方法注册")
                return True
            elif hasattr(frontend, 'register_built_in_panel'):
                # 尝试同步版本
                frontend.register_built_in_panel(
                    self.hass,
                    "iframe",
                    "EdgeSwitch",
                    "mdi:switch",
                    "edgeswitch",
                    {"url": "/edgeswitch_panel/index.html"},
                    require_admin=False,
                )
                self.registered = True
                _LOGGER.info("EdgeSwitch 面板已通过同步方法注册")
                return True
        except Exception as e:
            _LOGGER.debug("直接导入注册方法失败: %s", e)
        
        return False

    async def _try_event_based_registration(self) -> bool:
        """尝试基于事件的延迟注册。"""
        try:
            @callback
            def register_panel_on_start(event):
                """在 Home Assistant 启动完成后注册面板。"""
                self.hass.async_create_task(self._delayed_registration())

            # 如果 Home Assistant 已经启动，立即注册
            if self.hass.is_running:
                await self._delayed_registration()
            else:
                # 否则等待启动完成
                self.hass.bus.async_listen_once("homeassistant_started", register_panel_on_start)
                _LOGGER.info("EdgeSwitch 面板将在 Home Assistant 启动完成后注册")
            
            return True
        except Exception as e:
            _LOGGER.debug("事件基础注册方法失败: %s", e)
        
        return False

    async def _delayed_registration(self) -> None:
        """延迟注册面板。"""
        try:
            # 等待一小段时间确保所有组件都已加载
            await self.hass.async_add_executor_job(self._wait_and_register)
        except Exception as e:
            _LOGGER.error("延迟注册失败: %s", e)

    def _wait_and_register(self) -> None:
        """等待并注册面板。"""
        import time
        time.sleep(2)  # 等待2秒
        
        try:
            from homeassistant.components import frontend
            frontend.async_register_built_in_panel(
                self.hass,
                "iframe",
                "EdgeSwitch",
                "mdi:switch",
                "edgeswitch",
                {"url": "/edgeswitch_panel/index.html"},
                require_admin=False,
            )
            self.registered = True
            _LOGGER.info("EdgeSwitch 面板已延迟注册")
        except Exception as e:
            _LOGGER.debug("延迟注册也失败: %s", e)

    async def _try_manual_registration(self) -> bool:
        """尝试手动注册面板数据。"""
        try:
            # 直接操作 hass.data 中的面板数据
            if "frontend_panels" not in self.hass.data:
                self.hass.data["frontend_panels"] = {}
            
            # 添加面板配置
            panel_config = {
                "component_name": "iframe",
                "sidebar_title": "EdgeSwitch",
                "sidebar_icon": "mdi:switch",
                "frontend_url_path": "edgeswitch",
                "config": {"url": "/edgeswitch_panel/index.html"},
                "require_admin": False,
            }
            
            self.hass.data["frontend_panels"]["edgeswitch"] = panel_config
            
            # 触发前端更新
            self.hass.bus.async_fire("panels_updated")
            
            self.registered = True
            _LOGGER.info("EdgeSwitch 面板已通过手动方法注册")
            return True
            
        except Exception as e:
            _LOGGER.debug("手动注册方法失败: %s", e)
        
        return False

    async def async_unregister_panel(self) -> bool:
        """取消注册面板。"""
        try:
            if not self.registered:
                return True
            
            # 尝试从面板数据中移除
            if "frontend_panels" in self.hass.data:
                self.hass.data["frontend_panels"].pop("edgeswitch", None)
                self.hass.bus.async_fire("panels_updated")
            
            self.registered = False
            _LOGGER.info("EdgeSwitch 面板已取消注册")
            return True
            
        except Exception as e:
            _LOGGER.error("取消注册面板失败: %s", e)
            return False


# 全局注册管理器实例
_panel_manager: EdgeSwitchPanelRegistration | None = None


async def async_register_panel_to_sidebar(hass: HomeAssistant) -> bool:
    """注册面板到侧边栏 - 公共接口。"""
    global _panel_manager
    
    if _panel_manager is None:
        _panel_manager = EdgeSwitchPanelRegistration(hass)
    
    return await _panel_manager.async_register_panel()


async def async_unregister_panel_from_sidebar(hass: HomeAssistant) -> bool:
    """从侧边栏取消注册面板 - 公共接口。"""
    global _panel_manager
    
    if _panel_manager is not None:
        return await _panel_manager.async_unregister_panel()
    
    return True
