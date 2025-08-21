"""EdgeSwitch 配置流程。"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EdgeSwitchAPI
from .const import (
    CONF_UPDATE_INTERVAL,
    CONF_URL,
    CONF_VERIFY_SSL,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_INVALID_URL,
    ERROR_TIMEOUT,
    ERROR_UNKNOWN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# 配置表单架构
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
        vol.Optional(
            CONF_UPDATE_INTERVAL,
            default=DEFAULT_UPDATE_INTERVAL
        ): vol.All(vol.Coerce(int), vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL)),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """验证用户输入。
    
    Args:
        hass: Home Assistant 实例
        data: 用户输入的数据
        
    Returns:
        包含验证结果的字典
        
    Raises:
        各种异常，根据错误类型
    """
    # 创建 API 客户端
    api = EdgeSwitchAPI(
        url=data[CONF_URL],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
    )

    try:
        # 测试连接
        result = await api.test_connection()

        if not result["success"]:
            error_code = result["error_code"]
            error_msg = result["error"]

            if error_code == ERROR_INVALID_AUTH:
                raise InvalidAuth(error_msg)
            elif error_code == ERROR_CANNOT_CONNECT:
                raise CannotConnect(error_msg)
            elif error_code == ERROR_INVALID_URL:
                raise InvalidURL(error_msg)
            elif error_code == ERROR_TIMEOUT:
                raise ConnectionTimeout(error_msg)
            else:
                raise UnknownError(error_msg)

        # 返回连接信息
        return {
            "title": f"EdgeSwitch ({data[CONF_URL]})",
            "url": data[CONF_URL],
        }
    finally:
        # 确保 API 客户端正确关闭
        await api.close()


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """处理 EdgeSwitch 的配置流程。"""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        """获取选项流程。"""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """处理用户配置步骤。"""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = ERROR_CANNOT_CONNECT
            except InvalidAuth:
                errors["base"] = ERROR_INVALID_AUTH
            except InvalidURL:
                errors[CONF_URL] = ERROR_INVALID_URL
            except ConnectionTimeout:
                errors["base"] = ERROR_TIMEOUT
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("配置验证时发生未知错误")
                errors["base"] = ERROR_UNKNOWN
            else:
                # 检查是否已存在相同的配置
                await self.async_set_unique_id(user_input[CONF_URL])
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "url_example": "https://10.0.0.254",
            },
        )


class CannotConnect(Exception):
    """无法连接到设备的错误。"""


class InvalidAuth(Exception):
    """认证信息无效的错误。"""


class InvalidURL(Exception):
    """URL 格式无效的错误。"""


class ConnectionTimeout(Exception):
    """连接超时的错误。"""


class UnknownError(Exception):
    """未知错误。"""


class OptionsFlowHandler(config_entries.OptionsFlow):
    """处理 EdgeSwitch 的选项流程。"""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """初始化选项流程。"""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """处理选项配置的初始步骤。"""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # 获取当前配置的更新间隔
        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL,
            self.config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=current_interval,
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL)),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            description_placeholders={
                "min_interval": str(MIN_UPDATE_INTERVAL),
                "max_interval": str(MAX_UPDATE_INTERVAL),
                "current_interval": str(current_interval),
            },
        )
