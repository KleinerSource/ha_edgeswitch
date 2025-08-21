"""EdgeSwitch 组件的常量定义。"""
from __future__ import annotations

from typing import Final

# 组件域名
DOMAIN: Final = "edgeswitch"

# 配置键
CONF_URL: Final = "url"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_UPDATE_INTERVAL: Final = "update_interval"

# API 端点
API_LOGIN_ENDPOINT: Final = "/api/v1.0/user/login"
API_LOGOUT_ENDPOINT: Final = "/api/v1.0/user/logout"
API_DEVICE_ENDPOINT: Final = "/api/v1.0/device"
API_STATISTICS_ENDPOINT: Final = "/api/v1.0/statistics"
API_INTERFACES_ENDPOINT: Final = "/api/v1.0/interfaces"

# 默认值
DEFAULT_VERIFY_SSL: Final = False  # 默认禁用 SSL 验证，因为大多数设备使用自签名证书
DEFAULT_TIMEOUT: Final = 30
DEFAULT_UPDATE_INTERVAL: Final = 30  # 默认更新间隔（秒）

# 更新间隔限制
MIN_UPDATE_INTERVAL: Final = 5   # 最小更新间隔（秒）
MAX_UPDATE_INTERVAL: Final = 3600  # 最大更新间隔（秒，1小时）

# 错误代码
ERROR_CANNOT_CONNECT: Final = "cannot_connect"
ERROR_INVALID_AUTH: Final = "invalid_auth"
ERROR_INVALID_URL: Final = "invalid_url"
ERROR_TIMEOUT: Final = "timeout"
ERROR_UNKNOWN: Final = "unknown"

# 更新间隔（秒）- 保持向后兼容
UPDATE_INTERVAL: Final = DEFAULT_UPDATE_INTERVAL
