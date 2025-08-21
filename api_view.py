"""EdgeSwitch API 视图，为面板提供数据。"""
import logging
from typing import Any, Dict

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class EdgeSwitchAPIView(HomeAssistantView):
    """EdgeSwitch API 视图。"""

    url = "/api/edgeswitch/data"
    name = "api:edgeswitch:data"
    requires_auth = False  # 允许面板无认证访问

    def __init__(self, hass: HomeAssistant) -> None:
        """初始化 API 视图。"""
        self.hass = hass

    async def get(self, request: web.Request) -> web.Response:
        """获取 EdgeSwitch 数据。"""
        try:
            # 获取所有 EdgeSwitch 相关的实体状态
            data = await self._get_edgeswitch_data()
            return self.json(data)
        except Exception as e:
            _LOGGER.error("获取 EdgeSwitch 数据失败: %s", e)
            return self.json({"error": str(e)}, status_code=500)

    async def _get_edgeswitch_data(self) -> Dict[str, Any]:
        """获取 EdgeSwitch 数据。"""
        try:
            # 方法1: 尝试从 hass.data 获取 EdgeSwitch API 实例
            edgeswitch_data = self.hass.data.get(DOMAIN, {})
            if edgeswitch_data:
                _LOGGER.debug("找到 EdgeSwitch 数据: %d 个条目", len(edgeswitch_data))

                # 尝试从第一个可用的 API 实例获取数据
                for entry_id, api in edgeswitch_data.items():
                    if hasattr(api, 'get_statistics') and hasattr(api, 'get_interfaces'):
                        try:
                            _LOGGER.debug("尝试从 API 实例获取数据")

                            # 获取统计数据和接口数据
                            statistics_data = await api.get_statistics()
                            interfaces_data = await api.get_interfaces()

                            if statistics_data and interfaces_data:
                                return self._parse_api_data(statistics_data, interfaces_data)
                        except Exception as e:
                            _LOGGER.debug("从 API 实例获取数据失败: %s", e)
                            continue

            # 方法2: 尝试从实体状态获取数据
            _LOGGER.debug("尝试从实体状态获取数据")
            states = self._get_entity_states()
            if states:
                return self._parse_entity_states(states)

            # 如果所有方法都失败，抛出异常
            raise Exception("无法获取 EdgeSwitch 数据：所有数据源都不可用")

        except Exception as e:
            _LOGGER.error("获取 EdgeSwitch 数据失败: %s", e)
            raise

    def _get_entity_states(self) -> Dict[str, Any]:
        """获取实体状态。"""
        try:
            # 获取实体注册表
            entity_registry = async_get_entity_registry(self.hass)

            # 获取所有 EdgeSwitch 实体
            edgeswitch_entities = [
                entity for entity in entity_registry.entities.values()
                if entity.platform == DOMAIN
            ]

            # 获取实体状态
            states = {}
            for entity in edgeswitch_entities:
                state = self.hass.states.get(entity.entity_id)
                if state:
                    states[entity.entity_id] = {
                        "state": state.state,
                        "attributes": dict(state.attributes),
                        "entity_id": entity.entity_id,
                        "name": entity.name or state.name,
                    }

            return states
        except Exception as e:
            _LOGGER.debug("获取实体状态失败: %s", e)
            return {}

    def _parse_api_data(self, statistics_data: list, interfaces_data: list) -> Dict[str, Any]:
        """解析 API 数据。"""
        try:
            from .models import EdgeSwitchStatistics, EdgeSwitchInterfaceConfig

            # 解析统计数据
            statistics = EdgeSwitchStatistics.from_dict(statistics_data[0]) if statistics_data else None
            interfaces = EdgeSwitchInterfaceConfig.from_list(interfaces_data) if interfaces_data else None

            data = {
                "statistics": {
                    "cpuUsage": statistics.device.average_cpu_usage if statistics else 0,
                    "memoryUsage": statistics.device.ram.usage_percent if statistics else 0,
                    "temperature": statistics.device.max_temperature if statistics else 0,
                    "uptime": statistics.device.uptime if statistics else 0,
                    "totalThroughput": statistics.total_traffic_rate if statistics else 0,
                    "totalPoePower": statistics.total_poe_power if statistics else 0,
                    "activePorts": 0,
                    "activePoePorts": 0,
                },
                "interfaces": [],
                "device": {
                    "name": "EdgeSwitch",
                    "model": "ES-24-250W",
                    "version": "1.9.3",
                    "mac": "00:11:22:33:44:55"
                }
            }

            if interfaces and statistics:
                # 处理接口数据
                active_ports = 0
                active_poe_ports = 0
                port_interfaces = 0
                lag_interfaces = 0

                for interface in interfaces.interfaces:
                    interface_stats = statistics.get_interface_statistics(interface.identification.id)

                    # 计算活跃端口
                    if interface.status.plugged:
                        active_ports += 1

                    # 检查 PoE 功率消耗来判断是否真正在使用 PoE
                    if interface_stats and interface_stats.statistics.poe_power > 0:
                        active_poe_ports += 1

                    # 统计接口类型
                    if interface.identification.type == "port":
                        port_interfaces += 1
                    elif interface.identification.type == "lag":
                        lag_interfaces += 1

                    # 添加接口数据
                    interface_data = {
                        "id": interface.identification.id,
                        "name": interface.identification.name or f"Port {interface.identification.id}",
                        "type": interface.identification.type,  # 添加接口类型
                        "status": "connected" if interface.status.plugged else "disconnected",
                        "speed": interface.status.current_speed or "auto",
                        "traffic": interface_stats.statistics.rate if interface_stats else 0,
                        "rxTraffic": interface_stats.statistics.rx_rate if interface_stats else 0,
                        "txTraffic": interface_stats.statistics.tx_rate if interface_stats else 0,
                        "poeStatus": "active" if (interface_stats and interface_stats.statistics.poe_power > 0) else "disabled",
                        "poePower": interface_stats.statistics.poe_power if interface_stats else 0,
                    }

                    data["interfaces"].append(interface_data)

                # 更新统计数据
                data["statistics"]["activePorts"] = active_ports
                data["statistics"]["activePoePorts"] = active_poe_ports
                data["statistics"]["portInterfaces"] = port_interfaces
                data["statistics"]["lagInterfaces"] = lag_interfaces

            return data

        except Exception as e:
            _LOGGER.error("解析 API 数据失败: %s", e)
            raise



    def _parse_entity_states(self, states: Dict[str, Any]) -> Dict[str, Any]:
        """解析实体状态数据。"""
        data = {
            "statistics": {
                "cpuUsage": 0,
                "memoryUsage": 0,
                "temperature": 0,
                "uptime": 0,
                "totalThroughput": 0,
                "totalPoePower": 0,
                "activePorts": 0,
                "activePoePorts": 0,
            },
            "interfaces": [],
            "device": {
                "name": "EdgeSwitch",
                "model": "Unknown",
                "version": "Unknown",
                "mac": "Unknown",
            }
        }

        # 解析统计数据
        for entity_id, entity_data in states.items():
            state_value = entity_data["state"]
            
            try:
                if "cpu_usage" in entity_id:
                    data["statistics"]["cpuUsage"] = float(state_value) if state_value != "unknown" else 0
                elif "memory_usage" in entity_id:
                    data["statistics"]["memoryUsage"] = float(state_value) if state_value != "unknown" else 0
                elif "temperature" in entity_id:
                    data["statistics"]["temperature"] = float(state_value) if state_value != "unknown" else 0
                elif "uptime" in entity_id:
                    data["statistics"]["uptime"] = int(state_value) if state_value != "unknown" else 0
                elif "total_traffic" in entity_id:
                    data["statistics"]["totalThroughput"] = int(state_value) if state_value != "unknown" else 0
                elif "total_poe_power" in entity_id:
                    data["statistics"]["totalPoePower"] = float(state_value) if state_value != "unknown" else 0
                elif "connected_interfaces" in entity_id:
                    data["statistics"]["activePorts"] = int(state_value) if state_value != "unknown" else 0
                elif "active_poe_interfaces" in entity_id:
                    data["statistics"]["activePoePorts"] = int(state_value) if state_value != "unknown" else 0
                elif "device_info" in entity_id:
                    # 解析设备信息
                    attributes = entity_data.get("attributes", {})
                    data["device"]["name"] = attributes.get("device_name", "EdgeSwitch")
                    data["device"]["model"] = attributes.get("model", "Unknown")
                    data["device"]["version"] = attributes.get("firmware_version", "Unknown")
                    data["device"]["mac"] = attributes.get("mac_address", "Unknown")
            except (ValueError, TypeError):
                continue

        # 解析接口数据
        interface_data = {}
        
        for entity_id, entity_data in states.items():
            if "_interface_" in entity_id:
                # 提取接口ID
                parts = entity_id.split("_interface_")
                if len(parts) == 2:
                    interface_part = parts[1]
                    # 进一步分割以获取接口ID和传感器类型
                    if "_traffic" in interface_part:
                        interface_id = interface_part.replace("_traffic", "")
                        sensor_type = "traffic"
                    elif "_poe_power" in interface_part:
                        interface_id = interface_part.replace("_poe_power", "")
                        sensor_type = "poe_power"
                    elif "_config" in interface_part:
                        interface_id = interface_part.replace("_config", "")
                        sensor_type = "config"
                    else:
                        continue
                    
                    # 初始化接口数据
                    if interface_id not in interface_data:
                        interface_data[interface_id] = {
                            "id": interface_id,
                            "name": self._get_interface_name_from_entity(entity_data, interface_id),
                            "status": "unknown",
                            "speed": "Auto",
                            "traffic": 0,
                            "rxTraffic": 0,
                            "txTraffic": 0,
                            "poePower": 0,
                            "poeStatus": "inactive",
                            "enabled": True,
                            "plugged": False,
                        }
                    
                    # 填充数据
                    state_value = entity_data["state"]
                    attributes = entity_data.get("attributes", {})
                    
                    if sensor_type == "traffic":
                        try:
                            traffic = int(state_value) if state_value != "unknown" else 0
                            interface_data[interface_id]["traffic"] = traffic
                            # 模拟 RX/TX 分配 (60% RX, 40% TX)
                            interface_data[interface_id]["rxTraffic"] = int(traffic * 0.6)
                            interface_data[interface_id]["txTraffic"] = int(traffic * 0.4)
                        except (ValueError, TypeError):
                            pass
                    
                    elif sensor_type == "poe_power":
                        try:
                            poe_power = float(state_value) if state_value != "unknown" else 0
                            interface_data[interface_id]["poePower"] = poe_power
                            interface_data[interface_id]["poeStatus"] = "active" if poe_power > 0 else "inactive"
                        except (ValueError, TypeError):
                            pass
                    
                    elif sensor_type == "config":
                        # 解析配置状态
                        if "connected" in state_value.lower():
                            interface_data[interface_id]["status"] = "connected"
                            interface_data[interface_id]["plugged"] = True
                        elif "disconnected" in state_value.lower():
                            interface_data[interface_id]["status"] = "disconnected"
                            interface_data[interface_id]["plugged"] = False
                        else:
                            interface_data[interface_id]["status"] = "disabled"
                            interface_data[interface_id]["enabled"] = False
                        
                        # 从属性中获取速度信息
                        speed = attributes.get("current_speed", "Auto")
                        if speed and speed != "unknown":
                            interface_data[interface_id]["speed"] = self._format_speed(speed)

        # 转换为列表
        data["interfaces"] = list(interface_data.values())
        
        # 按接口ID排序
        data["interfaces"].sort(key=lambda x: self._sort_interface_id(x["id"]))

        return data

    def _get_interface_name_from_entity(self, entity_data: Dict[str, Any], interface_id: str) -> str:
        """从实体数据中获取接口名称。"""
        # 尝试从实体名称中提取接口名称
        entity_name = entity_data.get("name", "")
        if "Interface" in entity_name:
            parts = entity_name.split("Interface")
            if len(parts) > 1:
                name_part = parts[1].strip()
                # 移除传感器类型后缀
                for suffix in [" Traffic", " Config", " PoE Power"]:
                    if name_part.endswith(suffix):
                        name_part = name_part[:-len(suffix)].strip()
                        break
                if name_part and name_part != interface_id:
                    return name_part
        
        # 默认名称
        return f"Port {interface_id}"

    def _format_speed(self, speed: str) -> str:
        """格式化速度显示。"""
        if "1000" in speed:
            return "1 Gbps"
        elif "100" in speed:
            return "100 Mbps"
        elif "10" in speed:
            return "10 Mbps"
        else:
            return "Auto"

    def _sort_interface_id(self, interface_id: str) -> tuple:
        """接口ID排序键。"""
        try:
            if "/" in interface_id:
                parts = interface_id.split("/")
                return (int(parts[0]), int(parts[1]))
            else:
                return (0, int(interface_id))
        except (ValueError, IndexError):
            return (999, 999)


async def async_register_api_views(hass: HomeAssistant) -> None:
    """注册 API 视图。"""
    hass.http.register_view(EdgeSwitchAPIView(hass))
