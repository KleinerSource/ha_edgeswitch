"""EdgeSwitch 自定义组件，用于集成 Ubiquiti UniFi 交换机。"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .api import EdgeSwitchAPI
from .api_view import async_register_api_views
from .panel_view import async_register_panel_views
from .panel_registration import async_register_panel_to_sidebar, async_unregister_panel_from_sidebar

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置 EdgeSwitch 集成。"""
    _LOGGER.debug("设置 EdgeSwitch 集成，条目 ID: %s", entry.entry_id)
    
    # 创建 API 客户端
    api = EdgeSwitchAPI(
        url=entry.data["url"],
        username=entry.data["username"],
        password=entry.data["password"],
        verify_ssl=entry.data.get("verify_ssl", True)
    )
    
    # 测试连接
    try:
        await api.login()
        _LOGGER.info("成功连接到 EdgeSwitch: %s", entry.data["url"])
    except Exception as err:
        _LOGGER.error("无法连接到 EdgeSwitch: %s", err)
        raise ConfigEntryNotReady(f"无法连接到 EdgeSwitch: {err}") from err
    
    # 存储 API 实例
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = api
    
    # 设置平台
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 注册 API 视图
    await async_register_api_views(hass)

    # 注册面板视图
    await async_register_panel_views(hass)

    # 注册面板到侧边栏
    await async_register_panel_to_sidebar(hass)

    # 添加选项更新监听器
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载 EdgeSwitch 集成。"""
    _LOGGER.debug("卸载 EdgeSwitch 集成，条目 ID: %s", entry.entry_id)
    
    # 卸载平台
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # 清理 API 实例
        api = hass.data[DOMAIN].pop(entry.entry_id, None)
        if api:
            await api.close()

        # 移除面板（如果这是最后一个 EdgeSwitch 条目）
        if not hass.data[DOMAIN]:
            try:
                await async_unregister_panel_from_sidebar(hass)
            except Exception as e:
                _LOGGER.debug("移除面板时出错: %s", e)
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """重新加载 EdgeSwitch 集成。"""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
