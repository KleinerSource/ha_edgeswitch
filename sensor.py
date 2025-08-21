"""EdgeSwitch 传感器平台。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfDataRate,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import EdgeSwitchAPI, EdgeSwitchAPIError
from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN
from .models import EdgeSwitchDevice, EdgeSwitchStatistics, EdgeSwitchInterfaceConfig

_LOGGER = logging.getLogger(__name__)


def _get_interface_display_name(coordinator: "EdgeSwitchDataUpdateCoordinator", interface_id: str) -> str:
    """获取接口的显示名称。

    Args:
        coordinator: 数据协调器
        interface_id: 接口ID

    Returns:
        接口显示名称，优先使用 identification.name，否则使用 Port {interface_id} 格式
    """
    if not coordinator.data or "interfaces" not in coordinator.data:
        return f"Port {interface_id}"

    interfaces = coordinator.data["interfaces"]
    if not interfaces:
        return f"Port {interface_id}"

    # 查找对应的接口
    for interface in interfaces.interfaces:
        if interface.identification.id == interface_id:
            # 检查 name 字段是否有效
            name = interface.identification.name
            if name and name.strip():  # 不为空且不是空白字符串
                return name.strip()
            else:
                # 根据接口类型生成友好名称
                if interface.identification.type == "lag":
                    return f"LAG {interface_id}"
                else:
                    return f"Port {interface_id}"

    # 如果没找到接口，使用默认格式
    return f"Port {interface_id}"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置 EdgeSwitch 传感器。"""
    api: EdgeSwitchAPI = hass.data[DOMAIN][config_entry.entry_id]

    # 获取更新间隔配置
    update_interval = config_entry.options.get(
        CONF_UPDATE_INTERVAL,
        config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    )

    # 创建数据更新协调器
    coordinator = EdgeSwitchDataUpdateCoordinator(hass, api, update_interval)
    
    # 获取初始数据
    await coordinator.async_config_entry_first_refresh()
    
    # 创建传感器实体
    entities = [
        # 连接和设备信息传感器
        EdgeSwitchConnectionSensor(coordinator, config_entry),
        EdgeSwitchDeviceInfoSensor(coordinator, config_entry),
        EdgeSwitchPortCountSensor(coordinator, config_entry),
        EdgeSwitchPoePortCountSensor(coordinator, config_entry),
        EdgeSwitchSfpPortCountSensor(coordinator, config_entry),
        EdgeSwitchServicesSensor(coordinator, config_entry),

        # 统计传感器
        EdgeSwitchCPUSensor(coordinator, config_entry),
        EdgeSwitchMemorySensor(coordinator, config_entry),
        EdgeSwitchTemperatureSensor(coordinator, config_entry),
        EdgeSwitchUptimeSensor(coordinator, config_entry),
        EdgeSwitchTotalTrafficSensor(coordinator, config_entry),
        EdgeSwitchTotalPoePowerSensor(coordinator, config_entry),

        # 接口配置传感器
        EdgeSwitchConnectedInterfacesSensor(coordinator, config_entry),
        EdgeSwitchActivePoEInterfacesSensor(coordinator, config_entry),
        EdgeSwitchActiveLAGSensor(coordinator, config_entry),
    ]

    # 为活跃接口创建统计传感器
    if coordinator.data and "statistics" in coordinator.data and coordinator.data["statistics"]:
        statistics = coordinator.data["statistics"]
        # 为所有有流量的接口创建传感器
        active_interfaces = statistics.active_interfaces
        for interface in active_interfaces:
            entities.append(
                EdgeSwitchInterfaceTrafficSensor(coordinator, config_entry, interface.id)
            )
            if interface.statistics.is_poe_active:
                entities.append(
                    EdgeSwitchInterfacePoePowerSensor(coordinator, config_entry, interface.id)
                )

    # 为所有接口创建配置传感器
    if coordinator.data and "interfaces" in coordinator.data and coordinator.data["interfaces"]:
        interfaces = coordinator.data["interfaces"]
        # 为所有接口创建配置传感器（包括未连接的）
        all_interfaces = interfaces.interfaces
        for interface in all_interfaces:
            entities.append(
                EdgeSwitchInterfaceConfigSensor(coordinator, config_entry, interface.identification.id)
            )

    async_add_entities(entities)


class EdgeSwitchDataUpdateCoordinator(DataUpdateCoordinator):
    """EdgeSwitch 数据更新协调器。"""

    def __init__(self, hass: HomeAssistant, api: EdgeSwitchAPI, update_interval: int) -> None:
        """初始化协调器。"""
        self.api = api
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """获取最新数据。"""
        try:
            # 确保已登录
            if not self.api.is_logged_in():
                await self.api.login()

            # 获取设备信息
            device_data = await self.api.get_device_info()
            device = EdgeSwitchDevice.from_dict(device_data)

            # 获取统计信息
            statistics_data = await self.api.get_statistics()
            # 取第一个统计数据项（通常只有一个）
            statistics = None
            if statistics_data:
                statistics = EdgeSwitchStatistics.from_dict(statistics_data[0])

            # 获取接口配置信息
            interfaces_data = await self.api.get_interfaces()
            interfaces = EdgeSwitchInterfaceConfig.from_list(interfaces_data)

            return {
                "connected": True,
                "device": device,
                "statistics": statistics,
                "interfaces": interfaces,
                "last_update": datetime.now(timezone.utc),
            }
        except EdgeSwitchAPIError as err:
            raise UpdateFailed(f"获取数据失败: {err}") from err

    async def async_shutdown(self) -> None:
        """关闭协调器并清理资源。"""
        if self.api:
            await self.api.close()


class EdgeSwitchConnectionSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch 连接状态传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} Connection"
        self._attr_unique_id = f"{config_entry.entry_id}_connection"

    @property
    def state(self) -> str:
        """返回传感器状态。"""
        if self.coordinator.data and self.coordinator.data.get("connected"):
            return "connected"
        return "disconnected"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data:
            return {}
        
        return {
            "url": self._config_entry.data["url"],
            "username": self._config_entry.data["username"],
            "verify_ssl": self._config_entry.data.get("verify_ssl", True),
            "last_update": self.coordinator.data.get("last_update"),
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        if self.state == "connected":
            return "mdi:lan-connect"
        return "mdi:lan-disconnect"


class EdgeSwitchDeviceInfoSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch 设备信息传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} Device Info"
        self._attr_unique_id = f"{config_entry.entry_id}_device_info"

    @property
    def state(self) -> str:
        """返回传感器状态。"""
        if not self.coordinator.data or "device" not in self.coordinator.data:
            return "unknown"

        device = self.coordinator.data["device"]
        return device.identification.model

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "device" not in self.coordinator.data:
            return {}

        device = self.coordinator.data["device"]
        return {
            "mac_address": device.identification.mac,
            "model": device.identification.model,
            "family": device.identification.family,
            "product": device.identification.product,
            "firmware_version": device.identification.firmware_version,
            "firmware": device.identification.firmware,
            "server_version": device.identification.server_version,
            "bridge_version": device.identification.bridge_version,
            "subsystem_id": device.identification.subsystem_id,
            "error_codes": device.error_codes,
            "has_errors": device.has_errors,
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:router-network"


class EdgeSwitchPortCountSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch 端口数量传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} Port Count"
        self._attr_unique_id = f"{config_entry.entry_id}_port_count"
        self._attr_unit_of_measurement = "ports"

    @property
    def state(self) -> int:
        """返回传感器状态。"""
        if not self.coordinator.data or "device" not in self.coordinator.data:
            return 0

        device = self.coordinator.data["device"]
        return device.port_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "device" not in self.coordinator.data:
            return {}

        device = self.coordinator.data["device"]
        return {
            "total_ports": device.port_count,
            "poe_ports": device.poe_port_count,
            "sfp_ports": device.sfp_port_count,
            "lag_count": device.lag_count,
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:ethernet"


class EdgeSwitchPoePortCountSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch PoE 端口数量传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} PoE Ports"
        self._attr_unique_id = f"{config_entry.entry_id}_poe_ports"
        self._attr_unit_of_measurement = "ports"

    @property
    def state(self) -> int:
        """返回传感器状态。"""
        if not self.coordinator.data or "device" not in self.coordinator.data:
            return 0

        device = self.coordinator.data["device"]
        return device.poe_port_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "device" not in self.coordinator.data:
            return {}

        device = self.coordinator.data["device"]
        poe_interfaces = [
            interface for interface in device.capabilities.interfaces
            if interface.type == "port" and interface.support_poe
        ]

        return {
            "poe_port_count": device.poe_port_count,
            "total_port_count": device.port_count,
            "poe_values": list(set([
                value for interface in poe_interfaces
                for value in interface.poe_values
            ])),
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:power-plug"


class EdgeSwitchSfpPortCountSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch SFP 端口数量传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} SFP Ports"
        self._attr_unique_id = f"{config_entry.entry_id}_sfp_ports"
        self._attr_unit_of_measurement = "ports"

    @property
    def state(self) -> int:
        """返回传感器状态。"""
        if not self.coordinator.data or "device" not in self.coordinator.data:
            return 0

        device = self.coordinator.data["device"]
        return device.sfp_port_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "device" not in self.coordinator.data:
            return {}

        device = self.coordinator.data["device"]
        sfp_interfaces = [
            interface for interface in device.capabilities.interfaces
            if interface.type == "port" and interface.media == "SFP"
        ]

        return {
            "sfp_port_count": device.sfp_port_count,
            "total_port_count": device.port_count,
            "sfp_port_ids": [interface.id for interface in sfp_interfaces],
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:ethernet-cable"


class EdgeSwitchServicesSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch 服务传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} Services"
        self._attr_unique_id = f"{config_entry.entry_id}_services"

    @property
    def state(self) -> int:
        """返回传感器状态。"""
        if not self.coordinator.data or "device" not in self.coordinator.data:
            return 0

        device = self.coordinator.data["device"]
        return len(device.capabilities.services)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "device" not in self.coordinator.data:
            return {}

        device = self.coordinator.data["device"]
        return {
            "service_count": len(device.capabilities.services),
            "services": device.capabilities.services,
            "tools": device.capabilities.tools,
            "tool_count": len(device.capabilities.tools),
            "vlan_switching_supported": device.capabilities.vlan_switching.get("supported", False),
            "wifi_supported": device.capabilities.wifi.get("supported", False),
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:cog-outline"


class EdgeSwitchCPUSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch CPU 使用率传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} CPU Usage"
        self._attr_unique_id = f"{config_entry.entry_id}_cpu_usage"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_device_class = None  # CPU 使用率没有标准的 device_class

    @property
    def native_value(self) -> float:
        """返回传感器原始值。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return 0.0

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return 0.0

        return statistics.device.average_cpu_usage

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return {}

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return {}

        return {
            "cpu_count": len(statistics.device.cpu),
            "cpu_info": [
                {
                    "identifier": cpu.identifier,
                    "usage": cpu.usage,
                }
                for cpu in statistics.device.cpu
            ],
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:cpu-64-bit"


class EdgeSwitchMemorySensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch 内存使用率传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} Memory Usage"
        self._attr_unique_id = f"{config_entry.entry_id}_memory_usage"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_device_class = None  # 内存使用率没有标准的 device_class

    @property
    def native_value(self) -> float:
        """返回传感器原始值。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return 0.0

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return 0.0

        return round(statistics.device.ram.usage_percent, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return {}

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return {}

        ram = statistics.device.ram
        return {
            "total_bytes": ram.total,
            "used_bytes": ram.used,
            "free_bytes": ram.free,
            "total_mb": round(ram.total / 1024 / 1024, 1),
            "used_mb": round(ram.used / 1024 / 1024, 1),
            "free_mb": round(ram.free / 1024 / 1024, 1),
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:memory"


class EdgeSwitchTemperatureSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch 温度传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} Temperature"
        self._attr_unique_id = f"{config_entry.entry_id}_temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE

    @property
    def native_value(self) -> float:
        """返回传感器原始值。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return 0.0

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return 0.0

        return statistics.device.max_temperature

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return {}

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return {}

        return {
            "temperature_count": len(statistics.device.temperatures),
            "temperatures": [
                {
                    "name": temp.name,
                    "type": temp.type,
                    "value": temp.value,
                }
                for temp in statistics.device.temperatures
            ],
            "board_temperatures": [
                temp.value for temp in statistics.device.board_temperatures
            ],
            "poe_temperatures": [
                temp.value for temp in statistics.device.poe_temperatures
            ],
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:thermometer"


class EdgeSwitchUptimeSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch 运行时间传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} Uptime"
        self._attr_unique_id = f"{config_entry.entry_id}_uptime"
        self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
        self._attr_device_class = SensorDeviceClass.DURATION

    @property
    def native_value(self) -> int:
        """返回传感器原始值。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return 0

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return 0

        # 返回原始秒数，让 Home Assistant 处理时间格式化
        return statistics.device.uptime

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return {}

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return {}

        uptime = statistics.device.uptime
        days = uptime // 86400
        hours = (uptime % 86400) // 3600
        minutes = (uptime % 3600) // 60
        seconds = uptime % 60

        return {
            "uptime_seconds": uptime,
            "uptime_formatted": f"{days}d {hours}h {minutes}m {seconds}s",
            "uptime_days": days,
            "uptime_hours": hours,
            "uptime_minutes": minutes,
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:clock-outline"


class EdgeSwitchTotalTrafficSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch 总流量速率传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} Total Traffic"
        self._attr_unique_id = f"{config_entry.entry_id}_total_traffic"
        self._attr_native_unit_of_measurement = UnitOfDataRate.BITS_PER_SECOND
        self._attr_device_class = SensorDeviceClass.DATA_RATE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> int:
        """返回传感器原始值。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return 0

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return 0

        # 返回原始 bps 值，让 Home Assistant 处理单位转换
        return statistics.total_traffic_rate

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return {}

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return {}

        total_rate = statistics.total_traffic_rate
        active_interfaces = statistics.active_interfaces

        return {
            "total_rate": total_rate,
            "active_interface_count": len(active_interfaces),
            "active_interfaces": [
                {
                    "id": interface.id,
                    "name": interface.name,
                    "rate": interface.statistics.rate,
                    "tx_rate": interface.statistics.tx_rate,
                    "rx_rate": interface.statistics.rx_rate,
                }
                for interface in active_interfaces
            ],
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:speedometer"


class EdgeSwitchTotalPoePowerSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch 总 PoE 功率传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} Total PoE Power"
        self._attr_unique_id = f"{config_entry.entry_id}_total_poe_power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER

    @property
    def native_value(self) -> float:
        """返回传感器原始值。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return 0.0

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return 0.0

        return round(statistics.total_poe_power, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return {}

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return {}

        poe_interfaces = statistics.poe_interfaces

        return {
            "total_poe_power": statistics.total_poe_power,
            "active_poe_port_count": len(poe_interfaces),
            "poe_interfaces": [
                {
                    "id": interface.id,
                    "name": interface.name,
                    "power": interface.statistics.poe_power,
                }
                for interface in poe_interfaces
            ],
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:flash"


class EdgeSwitchInterfaceTrafficSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch 接口流量传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
        interface_id: str,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._interface_id = interface_id

        # 使用优化的接口名称显示逻辑
        interface_display_name = _get_interface_display_name(coordinator, interface_id)
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} Interface {interface_display_name} Traffic"
        self._attr_unique_id = f"{config_entry.entry_id}_interface_{interface_id}_traffic"
        self._attr_native_unit_of_measurement = UnitOfDataRate.BITS_PER_SECOND
        self._attr_device_class = SensorDeviceClass.DATA_RATE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> int:
        """返回传感器原始值。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return 0

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return 0

        interface_stats = statistics.get_interface_statistics(self._interface_id)
        if not interface_stats:
            return 0

        # 返回原始 bps 值，让 Home Assistant 处理单位转换
        return interface_stats.statistics.rate

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return {}

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return {}

        interface_stats = statistics.get_interface_statistics(self._interface_id)
        if not interface_stats:
            return {}

        stats = interface_stats.statistics
        return {
            "interface_id": self._interface_id,
            "interface_name": interface_stats.name,
            # 流量统计（原始 bps 值）
            "rate": stats.rate,
            "tx_rate": stats.tx_rate,
            "rx_rate": stats.rx_rate,
            # 字节统计
            "bytes": stats.bytes,
            "tx_bytes": stats.tx_bytes,
            "rx_bytes": stats.rx_bytes,
            # 包统计
            "packets": stats.packets,
            "tx_packets": stats.tx_packets,
            "rx_packets": stats.rx_packets,
            # 错误统计
            "errors": stats.errors,
            "dropped": stats.dropped,
            "has_errors": stats.has_errors,
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:ethernet-cable"


class EdgeSwitchInterfacePoePowerSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch 接口 PoE 功率传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
        interface_id: str,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._interface_id = interface_id

        # 使用优化的接口名称显示逻辑
        interface_display_name = _get_interface_display_name(coordinator, interface_id)
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} Interface {interface_display_name} PoE Power"
        self._attr_unique_id = f"{config_entry.entry_id}_interface_{interface_id}_poe_power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER

    @property
    def native_value(self) -> float:
        """返回传感器原始值。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return 0.0

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return 0.0

        interface_stats = statistics.get_interface_statistics(self._interface_id)
        if not interface_stats:
            return 0.0

        return round(interface_stats.statistics.poe_power, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "statistics" not in self.coordinator.data:
            return {}

        statistics = self.coordinator.data["statistics"]
        if not statistics:
            return {}

        interface_stats = statistics.get_interface_statistics(self._interface_id)
        if not interface_stats:
            return {}

        return {
            "interface_id": self._interface_id,
            "interface_name": interface_stats.name,
            "poe_power": interface_stats.statistics.poe_power,
            "is_poe_active": interface_stats.statistics.is_poe_active,
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:power-plug"


class EdgeSwitchConnectedInterfacesSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch 已连接接口传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} Connected Interfaces"
        self._attr_unique_id = f"{config_entry.entry_id}_connected_interfaces"
        self._attr_unit_of_measurement = "interfaces"

    @property
    def state(self) -> int:
        """返回传感器状态。"""
        if not self.coordinator.data or "interfaces" not in self.coordinator.data:
            return 0

        interfaces = self.coordinator.data["interfaces"]
        if not interfaces:
            return 0

        return len(interfaces.connected_interfaces)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "interfaces" not in self.coordinator.data:
            return {}

        interfaces = self.coordinator.data["interfaces"]
        if not interfaces:
            return {}

        connected = interfaces.connected_interfaces
        return {
            "connected_count": len(connected),
            "total_interfaces": len(interfaces.interfaces),
            "connected_interfaces": [
                {
                    "id": interface.identification.id,
                    "name": interface.identification.name,
                    "type": interface.identification.type,
                    "speed": interface.status.current_speed,
                    "stp_state": interface.stp_state,
                }
                for interface in connected[:10]  # 限制显示数量
            ],
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:ethernet-cable"


class EdgeSwitchActivePoEInterfacesSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch 活跃 PoE 接口传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} Active PoE Interfaces"
        self._attr_unique_id = f"{config_entry.entry_id}_active_poe_interfaces"
        self._attr_unit_of_measurement = "interfaces"

    @property
    def state(self) -> int:
        """返回传感器状态。"""
        if not self.coordinator.data or "interfaces" not in self.coordinator.data:
            return 0

        interfaces = self.coordinator.data["interfaces"]
        if not interfaces:
            return 0

        return len(interfaces.poe_active_interfaces)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "interfaces" not in self.coordinator.data:
            return {}

        interfaces = self.coordinator.data["interfaces"]
        if not interfaces:
            return {}

        poe_active = interfaces.poe_active_interfaces
        return {
            "active_poe_count": len(poe_active),
            "total_interfaces": len(interfaces.interfaces),
            "poe_interfaces": [
                {
                    "id": interface.identification.id,
                    "name": interface.identification.name,
                    "poe_mode": interface.port.poe if interface.port else "unknown",
                    "connected": interface.is_connected,
                }
                for interface in poe_active[:10]  # 限制显示数量
            ],
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:power-plug-outline"


class EdgeSwitchActiveLAGSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch 活跃 LAG 传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} Active LAGs"
        self._attr_unique_id = f"{config_entry.entry_id}_active_lags"
        self._attr_unit_of_measurement = "lags"

    @property
    def state(self) -> int:
        """返回传感器状态。"""
        if not self.coordinator.data or "interfaces" not in self.coordinator.data:
            return 0

        interfaces = self.coordinator.data["interfaces"]
        if not interfaces:
            return 0

        return len(interfaces.active_lag_interfaces)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "interfaces" not in self.coordinator.data:
            return {}

        interfaces = self.coordinator.data["interfaces"]
        if not interfaces:
            return {}

        active_lags = interfaces.active_lag_interfaces
        total_lags = interfaces.lag_interfaces

        return {
            "active_lag_count": len(active_lags),
            "total_lag_count": len(total_lags),
            "active_lags": [
                {
                    "id": interface.identification.id,
                    "name": interface.identification.name,
                    "member_count": interface.lag.member_count if interface.lag else 0,
                    "load_balance": interface.lag.load_balance if interface.lag else "unknown",
                    "stp_state": interface.stp_state,
                }
                for interface in active_lags
            ],
        }

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        return "mdi:link-variant"


class EdgeSwitchInterfaceConfigSensor(CoordinatorEntity, SensorEntity):
    """EdgeSwitch 接口配置传感器。"""

    def __init__(
        self,
        coordinator: EdgeSwitchDataUpdateCoordinator,
        config_entry: ConfigEntry,
        interface_id: str,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._interface_id = interface_id

        # 使用优化的接口名称显示逻辑
        interface_display_name = _get_interface_display_name(coordinator, interface_id)
        self._attr_name = f"EdgeSwitch {config_entry.data['url']} Interface {interface_display_name} Config"
        self._attr_unique_id = f"{config_entry.entry_id}_interface_{interface_id}_config"

    @property
    def state(self) -> str:
        """返回传感器状态。"""
        if not self.coordinator.data or "interfaces" not in self.coordinator.data:
            return "unknown"

        interfaces = self.coordinator.data["interfaces"]
        if not interfaces:
            return "unknown"

        interface = interfaces.get_interface_by_id(self._interface_id)
        if not interface:
            return "unknown"

        if interface.is_connected:
            return "connected"
        elif interface.status.enabled:
            return "enabled"
        else:
            return "disabled"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外的状态属性。"""
        if not self.coordinator.data or "interfaces" not in self.coordinator.data:
            return {}

        interfaces = self.coordinator.data["interfaces"]
        if not interfaces:
            return {}

        interface = interfaces.get_interface_by_id(self._interface_id)
        if not interface:
            return {}

        attributes = {
            "interface_id": interface.identification.id,
            "interface_name": interface.identification.name,
            "interface_type": interface.identification.type,
            "mac_address": interface.identification.mac,
            "enabled": interface.status.enabled,
            "plugged": interface.status.plugged,
            "current_speed": interface.status.current_speed,
            "configured_speed": interface.status.speed,
            "mtu": interface.status.mtu,
            "stp_state": interface.stp_state,
            "stp_forwarding": interface.is_stp_forwarding,
            "has_addresses": interface.has_addresses,
        }

        # 添加端口特定信息
        if interface.port:
            attributes.update({
                "poe_mode": interface.port.poe,
                "poe_active": interface.port.is_poe_active,
                "flow_control": interface.port.flow_control,
                "dhcp_snooping": interface.port.dhcp_snooping,
                "isolated": interface.port.isolated,
                "routed": interface.port.routed,
            })

            # SFP 信息
            if interface.port.sfp:
                attributes.update({
                    "sfp_present": interface.port.sfp.present,
                    "sfp_vendor": interface.port.sfp.vendor,
                    "sfp_part": interface.port.sfp.part,
                    "sfp_serial": interface.port.sfp.serial,
                })

            # Ping Watchdog 信息
            if interface.port.ping_watchdog:
                attributes.update({
                    "ping_watchdog_enabled": interface.port.ping_watchdog.enabled,
                    "ping_watchdog_address": interface.port.ping_watchdog.address,
                })

        # 添加 LAG 特定信息
        if interface.lag:
            attributes.update({
                "lag_member_count": interface.lag.member_count,
                "lag_load_balance": interface.lag.load_balance,
                "lag_static": interface.lag.static,
                "lag_link_trap": interface.lag.link_trap,
                "lag_members": [
                    {
                        "id": member.id,
                        "name": member.name,
                        "type": member.type,
                    }
                    for member in interface.lag.interfaces
                ],
            })

        # 添加 IP 地址信息
        if interface.addresses:
            attributes["addresses"] = [
                {
                    "type": addr.type,
                    "version": addr.version,
                    "cidr": addr.cidr,
                    "origin": addr.origin,
                }
                for addr in interface.addresses
            ]

        return attributes

    @property
    def icon(self) -> str:
        """返回传感器图标。"""
        if not self.coordinator.data or "interfaces" not in self.coordinator.data:
            return "mdi:ethernet"

        interfaces = self.coordinator.data["interfaces"]
        if not interfaces:
            return "mdi:ethernet"

        interface = interfaces.get_interface_by_id(self._interface_id)
        if not interface:
            return "mdi:ethernet"

        if interface.is_lag:
            return "mdi:link-variant"
        elif interface.is_sfp_port:
            return "mdi:ethernet-cable"
        elif interface.is_connected:
            return "mdi:ethernet-cable"
        else:
            return "mdi:ethernet"
