"""EdgeSwitch 数据模型定义。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DeviceIdentification:
    """设备标识信息。"""
    mac: str
    model: str
    family: str
    subsystem_id: str
    firmware_version: str
    firmware: str
    product: str
    server_version: str
    bridge_version: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceIdentification:
        """从字典创建设备标识信息。"""
        return cls(
            mac=data.get("mac", ""),
            model=data.get("model", ""),
            family=data.get("family", ""),
            subsystem_id=data.get("subsystemID", ""),
            firmware_version=data.get("firmwareVersion", ""),
            firmware=data.get("firmware", ""),
            product=data.get("product", ""),
            server_version=data.get("serverVersion", ""),
            bridge_version=data.get("bridgeVersion", ""),
        )


@dataclass
class InterfaceInfo:
    """接口信息。"""
    id: str
    type: str
    support_block: bool
    support_delete: bool
    support_reset: bool
    configurable: bool
    support_dhcp_snooping: bool
    support_isolate: bool
    support_auto_edge: bool
    max_mtu: int
    support_poe: bool
    support_cable_test: bool
    poe_values: list[str]
    media: str
    speed_values: list[str]
    # LAG 特有属性
    support_link_trap: bool
    load_balance_values: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterfaceInfo:
        """从字典创建接口信息。"""
        return cls(
            id=data.get("id", ""),
            type=data.get("type", ""),
            support_block=data.get("supportBlock", False),
            support_delete=data.get("supportDelete", False),
            support_reset=data.get("supportReset", False),
            configurable=data.get("configurable", False),
            support_dhcp_snooping=data.get("supportDHCPSnooping", False),
            support_isolate=data.get("supportIsolate", False),
            support_auto_edge=data.get("supportAutoEdge", False),
            max_mtu=data.get("maxMTU", 0),
            support_poe=data.get("supportPOE", False),
            support_cable_test=data.get("supportCableTest", False),
            poe_values=data.get("poeValues", []),
            media=data.get("media", ""),
            speed_values=data.get("speedValues", []),
            support_link_trap=data.get("supportLinkTrap", False),
            load_balance_values=data.get("loadBalanceValues", []),
        )


@dataclass
class DeviceCapabilities:
    """设备能力信息。"""
    interfaces: list[InterfaceInfo]
    services: list[str]
    device_features: dict[str, Any]
    tools: list[str]
    vlan_switching: dict[str, Any]
    uas: bool
    wifi: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceCapabilities:
        """从字典创建设备能力信息。"""
        interfaces = [
            InterfaceInfo.from_dict(interface_data)
            for interface_data in data.get("interfaces", [])
        ]
        
        return cls(
            interfaces=interfaces,
            services=data.get("services", []),
            device_features=data.get("device", {}),
            tools=data.get("tools", []),
            vlan_switching=data.get("vlanSwitching", {}),
            uas=data.get("uas", False),
            wifi=data.get("wifi", {}),
        )


@dataclass
class EdgeSwitchDevice:
    """EdgeSwitch 设备信息。"""
    error_codes: list[str]
    identification: DeviceIdentification
    capabilities: DeviceCapabilities

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EdgeSwitchDevice:
        """从 API 响应创建设备信息。"""
        return cls(
            error_codes=data.get("errorCodes", []),
            identification=DeviceIdentification.from_dict(
                data.get("identification", {})
            ),
            capabilities=DeviceCapabilities.from_dict(
                data.get("capabilities", {})
            ),
        )

    @property
    def has_errors(self) -> bool:
        """检查是否有错误。"""
        return len(self.error_codes) > 0

    @property
    def port_count(self) -> int:
        """获取端口数量。"""
        return len([
            interface for interface in self.capabilities.interfaces
            if interface.type == "port"
        ])

    @property
    def poe_port_count(self) -> int:
        """获取支持 PoE 的端口数量。"""
        return len([
            interface for interface in self.capabilities.interfaces
            if interface.type == "port" and interface.support_poe
        ])

    @property
    def sfp_port_count(self) -> int:
        """获取 SFP 端口数量。"""
        return len([
            interface for interface in self.capabilities.interfaces
            if interface.type == "port" and interface.media == "SFP"
        ])

    @property
    def lag_count(self) -> int:
        """获取 LAG 数量。"""
        return len([
            interface for interface in self.capabilities.interfaces
            if interface.type == "lag"
        ])

    def get_interface_by_id(self, interface_id: str) -> InterfaceInfo | None:
        """根据 ID 获取接口信息。"""
        for interface in self.capabilities.interfaces:
            if interface.id == interface_id:
                return interface
        return None


@dataclass
class CPUInfo:
    """CPU 信息。"""
    identifier: str
    usage: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CPUInfo:
        """从字典创建 CPU 信息。"""
        return cls(
            identifier=data.get("identifier", ""),
            usage=data.get("usage", 0),
        )


@dataclass
class RAMInfo:
    """内存信息。"""
    usage: int
    free: int
    total: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RAMInfo:
        """从字典创建内存信息。"""
        return cls(
            usage=data.get("usage", 0),
            free=data.get("free", 0),
            total=data.get("total", 0),
        )

    @property
    def used(self) -> int:
        """获取已使用内存。"""
        return self.total - self.free

    @property
    def usage_percent(self) -> float:
        """获取内存使用百分比。"""
        if self.total == 0:
            return 0.0
        return (self.used / self.total) * 100


@dataclass
class TemperatureInfo:
    """温度信息。"""
    name: str
    type: str
    value: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TemperatureInfo:
        """从字典创建温度信息。"""
        return cls(
            name=data.get("name", ""),
            type=data.get("type", ""),
            value=data.get("value", 0.0),
        )


@dataclass
class FanSpeedInfo:
    """风扇转速信息。"""
    name: str
    value: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FanSpeedInfo:
        """从字典创建风扇转速信息。"""
        return cls(
            name=data.get("name", ""),
            value=data.get("value", 0),
        )


@dataclass
class SFPInfo:
    """SFP 模块信息。"""
    temperature: float | None
    voltage: float | None
    current: float | None
    rx_power: float | None
    tx_power: float | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SFPInfo:
        """从字典创建 SFP 信息。"""
        return cls(
            temperature=data.get("temperature"),
            voltage=data.get("voltage"),
            current=data.get("current"),
            rx_power=data.get("rxPower"),
            tx_power=data.get("txPower"),
        )


@dataclass
class InterfaceStatistics:
    """接口统计信息。"""
    dropped: int
    errors: int
    tx_errors: int
    rx_errors: int
    rate: int
    tx_rate: int
    rx_rate: int
    bytes: int
    tx_bytes: int
    rx_bytes: int
    packets: int
    tx_packets: int
    rx_packets: int
    pps: int
    tx_pps: int
    rx_pps: int
    tx_jumbo: int
    rx_jumbo: int
    tx_flow_ctrl: int
    rx_flow_ctrl: int
    tx_broadcast: int
    rx_broadcast: int
    tx_multicast: int
    rx_multicast: int
    poe_power: float
    sfp: SFPInfo | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterfaceStatistics:
        """从字典创建接口统计信息。"""
        sfp_data = data.get("sfp")
        sfp = SFPInfo.from_dict(sfp_data) if sfp_data else None

        return cls(
            dropped=data.get("dropped", 0),
            errors=data.get("errors", 0),
            tx_errors=data.get("txErrors", 0),
            rx_errors=data.get("rxErrors", 0),
            rate=data.get("rate", 0),
            tx_rate=data.get("txRate", 0),
            rx_rate=data.get("rxRate", 0),
            bytes=data.get("bytes", 0),
            tx_bytes=data.get("txBytes", 0),
            rx_bytes=data.get("rxBytes", 0),
            packets=data.get("packets", 0),
            tx_packets=data.get("txPackets", 0),
            rx_packets=data.get("rxPackets", 0),
            pps=data.get("pps", 0),
            tx_pps=data.get("txPPS", 0),
            rx_pps=data.get("rxPPS", 0),
            tx_jumbo=data.get("txJumbo", 0),
            rx_jumbo=data.get("rxJumbo", 0),
            tx_flow_ctrl=data.get("txFlowCtrl", 0),
            rx_flow_ctrl=data.get("rxFlowCtrl", 0),
            tx_broadcast=data.get("txBroadcast", 0),
            rx_broadcast=data.get("rxBroadcast", 0),
            tx_multicast=data.get("txMulticast", 0),
            rx_multicast=data.get("rxMulticast", 0),
            poe_power=data.get("poePower", 0.0),
            sfp=sfp,
        )

    @property
    def has_traffic(self) -> bool:
        """检查是否有流量。"""
        return self.rate > 0 or self.bytes > 0

    @property
    def has_errors(self) -> bool:
        """检查是否有错误。"""
        return self.errors > 0 or self.dropped > 0

    @property
    def is_poe_active(self) -> bool:
        """检查 PoE 是否激活。"""
        return self.poe_power > 0.0


@dataclass
class InterfaceStatisticsInfo:
    """接口统计信息（包含接口 ID 和名称）。"""
    id: str
    name: str
    statistics: InterfaceStatistics

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterfaceStatisticsInfo:
        """从字典创建接口统计信息。"""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            statistics=InterfaceStatistics.from_dict(data.get("statistics", {})),
        )


@dataclass
class DeviceStatistics:
    """设备统计信息。"""
    cpu: list[CPUInfo]
    ram: RAMInfo
    temperatures: list[TemperatureInfo]
    power: list[dict[str, Any]]  # 暂时保持为字典，因为示例中为空
    storage: list[dict[str, Any]]  # 暂时保持为字典，因为示例中为空
    fan_speeds: list[FanSpeedInfo]
    uptime: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceStatistics:
        """从字典创建设备统计信息。"""
        return cls(
            cpu=[CPUInfo.from_dict(cpu_data) for cpu_data in data.get("cpu", [])],
            ram=RAMInfo.from_dict(data.get("ram", {})),
            temperatures=[
                TemperatureInfo.from_dict(temp_data)
                for temp_data in data.get("temperatures", [])
            ],
            power=data.get("power", []),
            storage=data.get("storage", []),
            fan_speeds=[
                FanSpeedInfo.from_dict(fan_data)
                for fan_data in data.get("fanSpeeds", [])
            ],
            uptime=data.get("uptime", 0),
        )

    @property
    def average_cpu_usage(self) -> float:
        """获取平均 CPU 使用率。"""
        if not self.cpu:
            return 0.0
        return sum(cpu.usage for cpu in self.cpu) / len(self.cpu)

    @property
    def max_temperature(self) -> float:
        """获取最高温度。"""
        if not self.temperatures:
            return 0.0
        return max(temp.value for temp in self.temperatures)

    @property
    def board_temperatures(self) -> list[TemperatureInfo]:
        """获取主板温度。"""
        return [temp for temp in self.temperatures if temp.type == "board"]

    @property
    def poe_temperatures(self) -> list[TemperatureInfo]:
        """获取 PoE 温度。"""
        return [temp for temp in self.temperatures if temp.type == "other" and "PoE" in temp.name]


@dataclass
class EdgeSwitchStatistics:
    """EdgeSwitch 统计信息。"""
    timestamp: int
    device: DeviceStatistics
    interfaces: list[InterfaceStatisticsInfo]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EdgeSwitchStatistics:
        """从字典创建统计信息。"""
        return cls(
            timestamp=data.get("timestamp", 0),
            device=DeviceStatistics.from_dict(data.get("device", {})),
            interfaces=[
                InterfaceStatisticsInfo.from_dict(interface_data)
                for interface_data in data.get("interfaces", [])
            ],
        )

    def get_interface_statistics(self, interface_id: str) -> InterfaceStatisticsInfo | None:
        """根据 ID 获取接口统计信息。"""
        for interface in self.interfaces:
            if interface.id == interface_id:
                return interface
        return None

    @property
    def active_interfaces(self) -> list[InterfaceStatisticsInfo]:
        """获取有流量的活跃接口。"""
        return [
            interface for interface in self.interfaces
            if interface.statistics.has_traffic
        ]

    @property
    def poe_interfaces(self) -> list[InterfaceStatisticsInfo]:
        """获取使用 PoE 的接口。"""
        return [
            interface for interface in self.interfaces
            if interface.statistics.is_poe_active
        ]

    @property
    def total_poe_power(self) -> float:
        """获取总 PoE 功率消耗。"""
        return sum(
            interface.statistics.poe_power
            for interface in self.interfaces
        )

    @property
    def total_traffic_rate(self) -> int:
        """获取总流量速率。"""
        return sum(
            interface.statistics.rate
            for interface in self.interfaces
        )

    @property
    def interfaces_with_errors(self) -> list[InterfaceStatisticsInfo]:
        """获取有错误的接口。"""
        return [
            interface for interface in self.interfaces
            if interface.statistics.has_errors
        ]


@dataclass
class InterfaceIdentification:
    """接口标识信息。"""
    id: str
    name: str
    mac: str
    type: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterfaceIdentification:
        """从字典创建接口标识信息。"""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            mac=data.get("mac", ""),
            type=data.get("type", ""),
        )


@dataclass
class InterfaceStatus:
    """接口状态信息。"""
    enabled: bool
    plugged: bool
    current_speed: str | None
    speed: str
    arp_proxy: bool
    mtu: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterfaceStatus:
        """从字典创建接口状态信息。"""
        return cls(
            enabled=data.get("enabled", False),
            plugged=data.get("plugged", False),
            current_speed=data.get("currentSpeed"),
            speed=data.get("speed", ""),
            arp_proxy=data.get("arpProxy", False),
            mtu=data.get("mtu", 0),
        )

    @property
    def is_connected(self) -> bool:
        """检查接口是否已连接。"""
        return self.enabled and self.plugged

    @property
    def speed_mbps(self) -> int | None:
        """获取速度（Mbps）。"""
        if not self.current_speed:
            return None

        # 解析速度字符串，如 "1000-full" -> 1000
        try:
            speed_str = self.current_speed.split("-")[0]
            return int(speed_str)
        except (ValueError, IndexError):
            return None


@dataclass
class InterfaceAddress:
    """接口地址信息。"""
    type: str
    version: str
    cidr: str
    eui64: bool
    origin: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterfaceAddress:
        """从字典创建接口地址信息。"""
        return cls(
            type=data.get("type", ""),
            version=data.get("version", ""),
            cidr=data.get("cidr", ""),
            eui64=data.get("eui64", False),
            origin=data.get("origin", ""),
        )


@dataclass
class STPConfig:
    """STP 配置信息。"""
    enabled: bool
    edge_port: str
    path_cost: int
    port_priority: int
    state: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> STPConfig:
        """从字典创建 STP 配置信息。"""
        return cls(
            enabled=data.get("enabled", False),
            edge_port=data.get("edgePort", ""),
            path_cost=data.get("pathCost", 0),
            port_priority=data.get("portPriority", 0),
            state=data.get("state", ""),
        )

    @property
    def is_forwarding(self) -> bool:
        """检查 STP 状态是否为转发。"""
        return self.state == "forwarding"


@dataclass
class PingWatchdogConfig:
    """Ping Watchdog 配置信息。"""
    enabled: bool
    address: str
    failure_count: int
    interval: int
    off_delay: int
    start_delay: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PingWatchdogConfig:
        """从字典创建 Ping Watchdog 配置信息。"""
        return cls(
            enabled=data.get("enabled", False),
            address=data.get("address", ""),
            failure_count=data.get("failureCount", 0),
            interval=data.get("interval", 0),
            off_delay=data.get("offDelay", 0),
            start_delay=data.get("startDelay", 0),
        )


@dataclass
class SFPConfig:
    """SFP 配置信息。"""
    present: bool
    vendor: str
    part: str
    serial: str
    tx_fault: bool | None
    los: bool | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SFPConfig:
        """从字典创建 SFP 配置信息。"""
        return cls(
            present=data.get("present", False),
            vendor=data.get("vendor", ""),
            part=data.get("part", ""),
            serial=data.get("serial", ""),
            tx_fault=data.get("txFault"),
            los=data.get("los"),
        )


@dataclass
class PortConfig:
    """端口配置信息。"""
    stp: STPConfig
    dhcp_snooping: bool
    poe: str
    flow_control: bool
    routed: bool
    isolated: bool
    ping_watchdog: PingWatchdogConfig | None
    sfp: SFPConfig | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PortConfig:
        """从字典创建端口配置信息。"""
        ping_watchdog_data = data.get("pingWatchdog")
        ping_watchdog = PingWatchdogConfig.from_dict(ping_watchdog_data) if ping_watchdog_data else None

        sfp_data = data.get("sfp")
        sfp = SFPConfig.from_dict(sfp_data) if sfp_data else None

        return cls(
            stp=STPConfig.from_dict(data.get("stp", {})),
            dhcp_snooping=data.get("dhcpSnooping", False),
            poe=data.get("poe", "off"),
            flow_control=data.get("flowControl", False),
            routed=data.get("routed", False),
            isolated=data.get("isolated", False),
            ping_watchdog=ping_watchdog,
            sfp=sfp,
        )

    @property
    def is_poe_active(self) -> bool:
        """检查 PoE 是否激活。"""
        return self.poe == "active"

    @property
    def is_sfp_port(self) -> bool:
        """检查是否为 SFP 端口。"""
        return self.sfp is not None


@dataclass
class LAGMemberInterface:
    """LAG 成员接口信息。"""
    id: str
    name: str
    mac: str
    type: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LAGMemberInterface:
        """从字典创建 LAG 成员接口信息。"""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            mac=data.get("mac", ""),
            type=data.get("type", ""),
        )


@dataclass
class LAGConfig:
    """LAG 配置信息。"""
    stp: STPConfig
    dhcp_snooping: bool
    static: bool
    link_trap: bool
    load_balance: str
    interfaces: list[LAGMemberInterface]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LAGConfig:
        """从字典创建 LAG 配置信息。"""
        return cls(
            stp=STPConfig.from_dict(data.get("stp", {})),
            dhcp_snooping=data.get("dhcpSnooping", False),
            static=data.get("static", False),
            link_trap=data.get("linkTrap", False),
            load_balance=data.get("loadBalance", ""),
            interfaces=[
                LAGMemberInterface.from_dict(interface_data)
                for interface_data in data.get("interfaces", [])
            ],
        )

    @property
    def member_count(self) -> int:
        """获取成员接口数量。"""
        return len(self.interfaces)

    @property
    def is_active(self) -> bool:
        """检查 LAG 是否激活（有成员接口）。"""
        return self.member_count > 0


@dataclass
class EdgeSwitchInterface:
    """EdgeSwitch 接口配置信息。"""
    identification: InterfaceIdentification
    status: InterfaceStatus
    addresses: list[InterfaceAddress]
    port: PortConfig | None
    lag: LAGConfig | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EdgeSwitchInterface:
        """从字典创建接口配置信息。"""
        port_data = data.get("port")
        port = PortConfig.from_dict(port_data) if port_data else None

        lag_data = data.get("lag")
        lag = LAGConfig.from_dict(lag_data) if lag_data else None

        return cls(
            identification=InterfaceIdentification.from_dict(data.get("identification", {})),
            status=InterfaceStatus.from_dict(data.get("status", {})),
            addresses=[
                InterfaceAddress.from_dict(addr_data)
                for addr_data in data.get("addresses", [])
            ],
            port=port,
            lag=lag,
        )

    @property
    def is_port(self) -> bool:
        """检查是否为端口接口。"""
        return self.identification.type == "port"

    @property
    def is_lag(self) -> bool:
        """检查是否为 LAG 接口。"""
        return self.identification.type == "lag"

    @property
    def is_connected(self) -> bool:
        """检查接口是否已连接。"""
        return self.status.is_connected

    @property
    def is_poe_active(self) -> bool:
        """检查 PoE 是否激活。"""
        if self.port:
            return self.port.is_poe_active
        return False

    @property
    def is_sfp_port(self) -> bool:
        """检查是否为 SFP 端口。"""
        if self.port:
            return self.port.is_sfp_port
        return False

    @property
    def stp_state(self) -> str:
        """获取 STP 状态。"""
        if self.port:
            return self.port.stp.state
        elif self.lag:
            return self.lag.stp.state
        return "unknown"

    @property
    def is_stp_forwarding(self) -> bool:
        """检查 STP 是否为转发状态。"""
        if self.port:
            return self.port.stp.is_forwarding
        elif self.lag:
            return self.lag.stp.is_forwarding
        return False

    @property
    def has_addresses(self) -> bool:
        """检查是否有 IP 地址。"""
        return len(self.addresses) > 0

    @property
    def primary_address(self) -> InterfaceAddress | None:
        """获取主要 IP 地址。"""
        if self.addresses:
            return self.addresses[0]
        return None


@dataclass
class EdgeSwitchInterfaceConfig:
    """EdgeSwitch 接口配置集合。"""
    interfaces: list[EdgeSwitchInterface]

    @classmethod
    def from_list(cls, data: list[dict[str, Any]]) -> EdgeSwitchInterfaceConfig:
        """从列表创建接口配置集合。"""
        return cls(
            interfaces=[
                EdgeSwitchInterface.from_dict(interface_data)
                for interface_data in data
            ]
        )

    def get_interface_by_id(self, interface_id: str) -> EdgeSwitchInterface | None:
        """根据 ID 获取接口配置。"""
        for interface in self.interfaces:
            if interface.identification.id == interface_id:
                return interface
        return None

    @property
    def port_interfaces(self) -> list[EdgeSwitchInterface]:
        """获取所有端口接口。"""
        return [interface for interface in self.interfaces if interface.is_port]

    @property
    def lag_interfaces(self) -> list[EdgeSwitchInterface]:
        """获取所有 LAG 接口。"""
        return [interface for interface in self.interfaces if interface.is_lag]

    @property
    def connected_interfaces(self) -> list[EdgeSwitchInterface]:
        """获取所有已连接的接口。"""
        return [interface for interface in self.interfaces if interface.is_connected]

    @property
    def poe_active_interfaces(self) -> list[EdgeSwitchInterface]:
        """获取所有 PoE 激活的接口。"""
        return [interface for interface in self.interfaces if interface.is_poe_active]

    @property
    def sfp_interfaces(self) -> list[EdgeSwitchInterface]:
        """获取所有 SFP 接口。"""
        return [interface for interface in self.interfaces if interface.is_sfp_port]

    @property
    def active_lag_interfaces(self) -> list[EdgeSwitchInterface]:
        """获取所有激活的 LAG 接口。"""
        return [
            interface for interface in self.lag_interfaces
            if interface.lag and interface.lag.is_active
        ]

    @property
    def interfaces_with_addresses(self) -> list[EdgeSwitchInterface]:
        """获取所有有 IP 地址的接口。"""
        return [interface for interface in self.interfaces if interface.has_addresses]
