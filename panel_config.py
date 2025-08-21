"""EdgeSwitch 面板配置。"""
import logging
import os
from homeassistant.core import HomeAssistant
from homeassistant.components.frontend import add_extra_js_url

_LOGGER = logging.getLogger(__name__)


async def async_register_panel(hass: HomeAssistant) -> bool:
    """注册 EdgeSwitch 面板。"""
    try:
        # 使用 Home Assistant 的标准面板注册方法
        await hass.components.frontend.async_register_built_in_panel(
            "iframe",
            "EdgeSwitch",
            "mdi:switch",
            "edgeswitch",
            {"url": "/edgeswitch_panel/index.html"},
            require_admin=False,
        )
        _LOGGER.info("EdgeSwitch 面板注册成功")
        return True

    except Exception as e:
        _LOGGER.error("注册 EdgeSwitch 面板失败: %s", e)

        # 备用方法：直接添加到前端面板数据
        try:
            if not hasattr(hass.data, 'frontend_panels'):
                hass.data['frontend_panels'] = {}

            hass.data['frontend_panels']['edgeswitch'] = {
                'component_name': 'iframe',
                'sidebar_title': 'EdgeSwitch',
                'sidebar_icon': 'mdi:switch',
                'frontend_url_path': 'edgeswitch',
                'config': {'url': '/edgeswitch_panel/index.html'},
                'require_admin': False,
            }

            _LOGGER.info("EdgeSwitch 面板备用注册成功")
            return True

        except Exception as e2:
            _LOGGER.error("EdgeSwitch 面板备用注册也失败: %s", e2)
            return False


def register_panel_resources(hass: HomeAssistant) -> None:
    """注册面板资源。"""
    try:
        # 注册静态文件路径
        panel_path = hass.config.path("custom_components/edgeswitch/panel")
        
        if os.path.exists(panel_path):
            hass.http.register_static_path(
                "/edgeswitch_panel",
                panel_path,
                cache_headers=False,
            )
            _LOGGER.info("EdgeSwitch 面板静态文件路径注册成功: %s", panel_path)
        else:
            _LOGGER.error("EdgeSwitch 面板目录不存在: %s", panel_path)
            
    except Exception as e:
        _LOGGER.error("注册 EdgeSwitch 面板资源失败: %s", e)


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """取消注册 EdgeSwitch 面板。"""
    try:
        # 移除面板
        if "frontend_panels" in hass.data and "edgeswitch_panel" in hass.data["frontend_panels"]:
            hass.data["frontend_panels"].pop("edgeswitch_panel", None)
            hass.bus.async_fire("panels_updated")
            _LOGGER.info("EdgeSwitch 面板已从侧边栏移除")
            
    except Exception as e:
        _LOGGER.error("移除 EdgeSwitch 面板失败: %s", e)
