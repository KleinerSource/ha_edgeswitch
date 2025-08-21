// EdgeSwitch 面板 JavaScript

class EdgeSwitchPanel {
    constructor() {
        this.refreshInterval = null;
        this.autoRefreshEnabled = true;
        this.isRefreshing = false;
        this.lastData = null;
        this.lastUpdateTime = null;
        this.refreshQueue = [];
        this.animationDuration = 300; // 动画持续时间(ms)
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setupVisibilityHandling();
        this.loadData();
        this.startAutoRefresh();
    }

    setupEventListeners() {
        // 刷新按钮
        document.getElementById('refreshBtn').addEventListener('click', () => {
            this.loadData();
        });

        // 自动刷新切换
        document.getElementById('autoRefresh').addEventListener('change', (e) => {
            this.autoRefreshEnabled = e.target.checked;
            if (this.autoRefreshEnabled) {
                this.startAutoRefresh();
            } else {
                this.stopAutoRefresh();
            }
        });
    }

    async loadData(forceRefresh = false) {
        // 防止重复刷新
        if (this.isRefreshing && !forceRefresh) {
            console.debug('数据刷新进行中，跳过此次请求');
            return;
        }

        try {
            this.isRefreshing = true;

            // 只在首次加载时显示加载状态
            if (!this.lastData || forceRefresh) {
                this.showLoading();
            }

            this.updateConnectionStatus('connecting', '连接中...');

            // 获取 Home Assistant API 数据
            const data = await this.fetchEdgeSwitchData();

            if (data && data.statistics && data.interfaces) {
                // 增量更新数据
                await this.incrementalUpdate(data);

                // 更新最后数据和时间
                this.lastData = JSON.parse(JSON.stringify(data)); // 深拷贝
                this.lastUpdateTime = new Date();

                this.hideLoading();
                this.updateConnectionStatus('connected', '已连接');

                // 更新最后更新时间显示
                this.updateLastRefreshTime();

            } else {
                throw new Error('无法获取 EdgeSwitch 数据');
            }
        } catch (error) {
            console.error('加载数据失败:', error);
            this.updateConnectionStatus('error', '连接失败');
            this.showError(error.message);
        } finally {
            this.isRefreshing = false;
        }
    }

    async fetchEdgeSwitchData() {
        try {
            // 尝试多种方式获取数据
            let data = null;

            // 方法1: 尝试使用专用的 EdgeSwitch API 端点
            try {
                const response = await fetch('/api/edgeswitch/data', {
                    credentials: 'same-origin',  // 使用同源凭据
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });

                if (response.ok) {
                    data = await response.json();
                    if (!data.error) {
                        console.log('通过专用 API 获取数据成功');
                        return data;
                    }
                }
            } catch (e) {
                console.debug('专用 API 调用失败:', e);
            }

            // 方法2: 尝试通过父窗口获取数据
            try {
                if (window.parent && window.parent !== window) {
                    data = await this.fetchDataFromParent();
                    if (data) {
                        console.log('通过父窗口获取数据成功');
                        return data;
                    }
                }
            } catch (e) {
                console.debug('父窗口数据获取失败:', e);
            }

            // 如果所有方法都失败，返回错误
            throw new Error('无法获取 EdgeSwitch 数据：所有数据源都不可用');

        } catch (error) {
            console.error('获取 API 数据失败:', error);
            // 如果所有方法都失败，抛出异常
            throw error;
        }
    }

    async fetchDataFromParent() {
        try {
            // 尝试通过 postMessage 与父窗口通信
            return new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    reject(new Error('父窗口通信超时'));
                }, 5000);

                const messageHandler = (event) => {
                    if (event.data && event.data.type === 'edgeswitch_data') {
                        clearTimeout(timeout);
                        window.removeEventListener('message', messageHandler);
                        resolve(event.data.data);
                    }
                };

                window.addEventListener('message', messageHandler);

                // 向父窗口请求数据
                window.parent.postMessage({
                    type: 'request_edgeswitch_data'
                }, '*');
            });
        } catch (error) {
            console.debug('父窗口通信失败:', error);
            return null;
        }
    }

    getAccessToken() {
        // 在 iframe 环境中，通常不需要手动获取令牌
        // Home Assistant 会自动处理认证
        return null;
    }

    async incrementalUpdate(newData) {
        // 增量更新数据，只更新发生变化的部分
        try {
            // 如果是首次加载，执行完整更新
            if (!this.lastData) {
                this.updateStatistics(newData.statistics);
                this.updatePortVisualization(newData.interfaces, newData.statistics);
                this.updatePortTable(newData.interfaces, newData.statistics);
                return;
            }

            // 检测统计数据变化
            const statsChanges = this.detectStatisticsChanges(this.lastData.statistics, newData.statistics);
            if (statsChanges.length > 0) {
                await this.updateStatisticsIncremental(newData.statistics, statsChanges);
            }

            // 检测接口数据变化
            const interfaceChanges = this.detectInterfaceChanges(this.lastData.interfaces, newData.interfaces);
            if (interfaceChanges.length > 0) {
                await this.updateInterfacesIncremental(newData.interfaces, newData.statistics, interfaceChanges);
            }

            console.debug(`增量更新完成: ${statsChanges.length} 个统计变化, ${interfaceChanges.length} 个接口变化`);

        } catch (error) {
            console.error('增量更新失败:', error);
            // 回退到完整更新
            this.updateStatistics(newData.statistics);
            this.updatePortVisualization(newData.interfaces, newData.statistics);
            this.updatePortTable(newData.interfaces, newData.statistics);
        }
    }

    detectStatisticsChanges(oldStats, newStats) {
        // 检测统计数据变化
        const changes = [];
        const keys = ['cpuUsage', 'memoryUsage', 'temperature', 'totalThroughput', 'totalPoePower', 'activePorts', 'activePoePorts'];

        for (const key of keys) {
            const oldValue = oldStats[key];
            const newValue = newStats[key];

            // 数值变化检测（考虑浮点数精度）
            if (typeof oldValue === 'number' && typeof newValue === 'number') {
                if (Math.abs(oldValue - newValue) > 0.01) {
                    changes.push({
                        field: key,
                        oldValue: oldValue,
                        newValue: newValue,
                        change: newValue - oldValue
                    });
                }
            } else if (oldValue !== newValue) {
                changes.push({
                    field: key,
                    oldValue: oldValue,
                    newValue: newValue
                });
            }
        }

        return changes;
    }

    detectInterfaceChanges(oldInterfaces, newInterfaces) {
        // 检测接口数据变化
        const changes = [];

        // 创建接口映射以便快速查找
        const oldInterfaceMap = new Map();
        const newInterfaceMap = new Map();

        oldInterfaces.forEach(intf => oldInterfaceMap.set(intf.id, intf));
        newInterfaces.forEach(intf => newInterfaceMap.set(intf.id, intf));

        // 检测变化
        for (const [id, newInterface] of newInterfaceMap) {
            const oldInterface = oldInterfaceMap.get(id);

            if (!oldInterface) {
                // 新增接口
                changes.push({
                    type: 'added',
                    id: id,
                    interface: newInterface
                });
            } else {
                // 检测接口属性变化
                const interfaceChanges = this.detectSingleInterfaceChanges(oldInterface, newInterface);
                if (interfaceChanges.length > 0) {
                    changes.push({
                        type: 'modified',
                        id: id,
                        interface: newInterface,
                        changes: interfaceChanges
                    });
                }
            }
        }

        // 检测删除的接口
        for (const [id, oldInterface] of oldInterfaceMap) {
            if (!newInterfaceMap.has(id)) {
                changes.push({
                    type: 'removed',
                    id: id,
                    interface: oldInterface
                });
            }
        }

        return changes;
    }

    detectSingleInterfaceChanges(oldInterface, newInterface) {
        // 检测单个接口的变化
        const changes = [];
        const keys = ['status', 'traffic', 'rxTraffic', 'txTraffic', 'poeStatus', 'poePower', 'speed'];

        for (const key of keys) {
            const oldValue = oldInterface[key];
            const newValue = newInterface[key];

            if (typeof oldValue === 'number' && typeof newValue === 'number') {
                if (Math.abs(oldValue - newValue) > 0.01) {
                    changes.push({
                        field: key,
                        oldValue: oldValue,
                        newValue: newValue,
                        change: newValue - oldValue
                    });
                }
            } else if (oldValue !== newValue) {
                changes.push({
                    field: key,
                    oldValue: oldValue,
                    newValue: newValue
                });
            }
        }

        return changes;
    }

    parseEntityData(entities) {
        const data = {
            statistics: {},
            interfaces: []
        };

        // 解析统计数据
        entities.forEach(entity => {
            const entityId = entity.entity_id;
            
            if (entityId.includes('_cpu_usage')) {
                data.statistics.cpuUsage = parseFloat(entity.state) || 0;
            } else if (entityId.includes('_total_traffic')) {
                data.statistics.totalThroughput = parseInt(entity.state) || 0;
            } else if (entityId.includes('_total_poe_power')) {
                data.statistics.totalPoePower = parseFloat(entity.state) || 0;
            } else if (entityId.includes('_connected_interfaces')) {
                data.statistics.activePorts = parseInt(entity.state) || 0;
            }
        });

        // 解析接口数据（这里需要根据实际的传感器结构调整）
        const interfaceEntities = entities.filter(e => 
            e.entity_id.includes('_interface_') && 
            (e.entity_id.includes('_traffic') || e.entity_id.includes('_config') || e.entity_id.includes('_poe_power'))
        );

        // 按接口ID分组
        const interfaceGroups = {};
        interfaceEntities.forEach(entity => {
            const match = entity.entity_id.match(/_interface_([^_]+)_/);
            if (match) {
                const interfaceId = match[1];
                if (!interfaceGroups[interfaceId]) {
                    interfaceGroups[interfaceId] = {};
                }
                
                if (entity.entity_id.includes('_traffic')) {
                    interfaceGroups[interfaceId].traffic = parseInt(entity.state) || 0;
                } else if (entity.entity_id.includes('_config')) {
                    interfaceGroups[interfaceId].config = entity.state;
                } else if (entity.entity_id.includes('_poe_power')) {
                    interfaceGroups[interfaceId].poePower = parseFloat(entity.state) || 0;
                }
            }
        });

        // 转换为接口数组
        Object.keys(interfaceGroups).forEach(interfaceId => {
            const group = interfaceGroups[interfaceId];
            data.interfaces.push({
                id: interfaceId,
                name: `Port ${interfaceId}`,
                status: group.config || 'unknown',
                traffic: group.traffic || 0,
                poePower: group.poePower || 0,
                speed: this.getInterfaceSpeed(group.config),
                poeStatus: group.poePower > 0 ? 'active' : 'inactive'
            });
        });

        return data;
    }



    getInterfaceSpeed(config) {
        if (config && config.includes('1000')) return '1 Gbps';
        if (config && config.includes('100')) return '100 Mbps';
        if (config && config.includes('10')) return '10 Mbps';
        return 'Auto';
    }



    async updateStatisticsIncremental(stats, changes) {
        // 增量更新统计数据
        for (const change of changes) {
            const element = this.getStatisticElement(change.field);
            if (element) {
                await this.animateValueChange(element, change.oldValue, change.newValue, change.field);
            }
        }
    }

    getStatisticElement(field) {
        // 获取统计数据对应的DOM元素
        const elementMap = {
            'cpuUsage': 'cpuUsage',
            'memoryUsage': 'memoryUsage',
            'temperature': 'temperature',
            'totalThroughput': 'totalThroughput',
            'totalPoePower': 'totalPoePower',
            'activePorts': 'activePorts',
            'activePoePorts': 'activePoePorts',
            'portInterfaces': 'portInterfaces',
            'lagInterfaces': 'lagInterfaces'
        };

        const elementId = elementMap[field];
        return elementId ? document.getElementById(elementId) : null;
    }

    async animateValueChange(element, oldValue, newValue, field) {
        // 为数值变化添加动画效果
        if (!element) return;

        // 添加变化指示类
        element.classList.add('value-changing');

        // 根据变化方向添加不同的类
        const change = newValue - oldValue;
        if (change > 0) {
            element.classList.add('value-increasing');
        } else if (change < 0) {
            element.classList.add('value-decreasing');
        }

        // 更新数值
        const formattedValue = this.formatStatisticValue(newValue, field);
        element.textContent = formattedValue;

        // 动画完成后移除类
        setTimeout(() => {
            element.classList.remove('value-changing', 'value-increasing', 'value-decreasing');
        }, this.animationDuration);
    }

    formatStatisticValue(value, field) {
        // 格式化统计数值
        switch (field) {
            case 'cpuUsage':
            case 'memoryUsage':
                return value.toFixed(1) + '%';
            case 'temperature':
                return value.toFixed(1) + '°C';
            case 'totalThroughput':
                return this.formatTraffic(value);
            case 'totalPoePower':
                return value.toFixed(1) + ' W';
            case 'activePorts':
                return `${value}/24`;
            case 'activePoePorts':
            case 'portInterfaces':
            case 'lagInterfaces':
                return value.toString();
            default:
                return value.toString();
        }
    }

    updateStatistics(stats) {
        document.getElementById('totalThroughput').textContent = this.formatTraffic(stats.totalThroughput);
        document.getElementById('activePorts').textContent = `${stats.activePorts}/24`;
        document.getElementById('totalPoePower').textContent = `${stats.totalPoePower.toFixed(1)} W`;
        document.getElementById('cpuUsage').textContent = `${stats.cpuUsage.toFixed(1)}%`;

        // 更新接口类型统计
        if (stats.portInterfaces !== undefined) {
            document.getElementById('portInterfaces').textContent = stats.portInterfaces;
        }
        if (stats.lagInterfaces !== undefined) {
            document.getElementById('lagInterfaces').textContent = stats.lagInterfaces;
        }
    }

    async updateInterfacesIncremental(interfaces, statistics, changes) {
        // 增量更新接口数据
        const promises = [];

        for (const change of changes) {
            if (change.type === 'modified') {
                // 更新端口可视化
                promises.push(this.updateSinglePortVisualization(change.id, change.interface));

                // 更新端口表格行
                promises.push(this.updateSinglePortTableRow(change.id, change.interface, change.changes));
            }
        }

        await Promise.all(promises);
    }

    async updateSinglePortVisualization(portId, portInterface) {
        // 更新单个端口的可视化
        const portNumber = parseInt(portId.split('/')[1]);
        const portElement = document.querySelector(`.port-item:nth-child(${portNumber})`);

        if (portElement) {
            // 移除所有状态类
            portElement.classList.remove('active', 'inactive', 'poe', 'disabled', 'port-interface', 'lag-interface');

            // 添加接口类型类
            if (portInterface.type === 'lag') {
                portElement.classList.add('lag-interface');
            } else {
                portElement.classList.add('port-interface');
            }

            // 添加新状态类
            if (portInterface.status === 'connected') {
                // 检查是否真正在使用 PoE（有功率消耗）
                if (portInterface.poePower > 0) {
                    portElement.classList.add('poe');
                } else {
                    portElement.classList.add('active');
                }
            } else if (portInterface.status === 'disconnected') {
                portElement.classList.add('inactive');
            } else {
                portElement.classList.add('disabled');
            }

            // 更新工具提示
            portElement.title = `${portInterface.name}\n状态: ${portInterface.status}\n流量: ${this.formatTraffic(portInterface.traffic)}`;

            // 添加更新动画
            portElement.classList.add('port-updated');
            setTimeout(() => {
                portElement.classList.remove('port-updated');
            }, this.animationDuration);
        }
    }

    async updateSinglePortTableRow(portId, portInterface, changes) {
        // 更新单个端口的表格行
        const row = document.querySelector(`tr[data-port-id="${portId.replace('/', '_')}"]`);
        if (!row) return;

        // 为每个变化的字段添加动画
        for (const change of changes) {
            const cell = this.getPortTableCell(row, change.field);
            if (cell) {
                await this.animatePortCellChange(cell, change, portInterface);
            }
        }
    }

    getPortTableCell(row, field) {
        // 获取端口表格行中对应字段的单元格
        const cellMap = {
            'status': 2,
            'speed': 3,
            'rxTraffic': 4,
            'txTraffic': 5,
            'poeStatus': 6,
            'poePower': 7
        };

        const cellIndex = cellMap[field];
        return cellIndex ? row.cells[cellIndex] : null;
    }

    async animatePortCellChange(cell, change, portInterface) {
        //为端口表格单元格变化添加动画。
        if (!cell) return;

        // 添加变化动画类
        cell.classList.add('cell-changing');

        // 更新单元格内容
        this.updatePortCellContent(cell, change.field, portInterface);

        // 动画完成后移除类
        setTimeout(() => {
            cell.classList.remove('cell-changing');
        }, this.animationDuration);
    }

    updatePortCellContent(cell, field, portInterface) {
        //更新端口表格单元格内容。
        switch (field) {
            case 'status':
                cell.innerHTML = `
                    <div class="status-indicator ${portInterface.status}">
                        <div class="status-dot ${portInterface.status}"></div>
                        ${this.getStatusText(portInterface.status)}
                    </div>
                `;
                break;
            case 'speed':
                cell.textContent = portInterface.speed;
                break;
            case 'rxTraffic':
                cell.textContent = this.formatTraffic(portInterface.rxTraffic || 0);
                break;
            case 'txTraffic':
                cell.textContent = this.formatTraffic(portInterface.txTraffic || 0);
                break;
            case 'poeStatus':
                cell.innerHTML = `
                    <div class="poe-status ${portInterface.poePower > 0 ? 'active' : 'disabled'}">
                        ${portInterface.poePower > 0 ? '使用中' : '未使用'}
                    </div>
                `;
                break;
            case 'poePower':
                cell.textContent = portInterface.poePower > 0 ? portInterface.poePower.toFixed(1) + ' W' : '--';
                break;
            case 'actions':
                // 更新操作按钮（保持禁用状态）
                cell.innerHTML = `
                    <button class="action-btn disabled" disabled title="端口控制功能开发中">
                        ${portInterface.status === 'connected' ? '禁用' : '启用'}
                    </button>
                `;
                break;
        }
    }

    updatePortVisualization(interfaces, stats) {
        const portGrid = document.getElementById('portGrid');
        portGrid.innerHTML = '';

        // 创建24个端口的可视化（假设是24端口交换机）
        for (let i = 1; i <= 24; i++) {
            const portId = `0/${i}`;
            const portInterface = interfaces.find(intf => intf.id === portId);

            const portItem = document.createElement('div');
            portItem.className = 'port-item';
            portItem.textContent = i;

            if (portInterface) {
                // 添加接口类型类
                if (portInterface.type === 'lag') {
                    portItem.classList.add('lag-interface');
                } else {
                    portItem.classList.add('port-interface');
                }

                if (portInterface.status === 'connected') {
                    // 检查是否真正在使用 PoE（有功率消耗）
                    if (portInterface.poePower > 0) {
                        portItem.classList.add('poe');
                    } else {
                        portItem.classList.add('active');
                    }
                } else if (portInterface.status === 'disconnected') {
                    portItem.classList.add('inactive');
                } else {
                    portItem.classList.add('disabled');
                }

                portItem.title = `${portInterface.name}\n状态: ${portInterface.status}\n流量: ${this.formatTraffic(portInterface.traffic)}`;
            } else {
                portItem.classList.add('inactive');
                portItem.title = `端口 ${i}\n状态: 未连接`;
            }

            portGrid.appendChild(portItem);
        }
    }

    updatePortTable(interfaces, stats) {
        const tbody = document.getElementById('portTableBody');
        tbody.innerHTML = '';

        interfaces.forEach(portInterface => {
            const row = document.createElement('tr');
            row.setAttribute('data-port-id', portInterface.id.replace('/', '_'));

            row.innerHTML = `
                <td><strong>${portInterface.id}</strong></td>
                <td>
                    <div class="interface-name">
                        ${portInterface.name}
                        <span class="interface-type ${portInterface.type}">${this.getInterfaceTypeText(portInterface.type)}</span>
                    </div>
                </td>
                <td>
                    <div class="status-indicator ${portInterface.status}">
                        <div class="status-dot ${portInterface.status}"></div>
                        ${this.getStatusText(portInterface.status)}
                    </div>
                </td>
                <td>${portInterface.speed}</td>
                <td>${this.formatTraffic(portInterface.rxTraffic || 0)}</td>
                <td>${this.formatTraffic(portInterface.txTraffic || 0)}</td>
                <td>
                    <div class="poe-status ${portInterface.poePower > 0 ? 'active' : 'disabled'}">
                        ${portInterface.poePower > 0 ? '使用中' : '未使用'}
                    </div>
                </td>
                <td>${portInterface.poePower > 0 ? portInterface.poePower.toFixed(1) + ' W' : '--'}</td>
                <td>Auto</td>
                <td>
                    <button class="action-btn disabled" disabled title="端口控制功能开发中">
                        ${portInterface.status === 'connected' ? '禁用' : '启用'}
                    </button>
                </td>
            `;

            tbody.appendChild(row);
        });
    }

    formatTraffic(bps) {
        if (bps >= 1000000000) {
            return `${(bps / 1000000000).toFixed(2)} Gbps`;
        } else if (bps >= 1000000) {
            return `${(bps / 1000000).toFixed(2)} Mbps`;
        } else if (bps >= 1000) {
            return `${(bps / 1000).toFixed(2)} Kbps`;
        } else {
            return `${bps} bps`;
        }
    }

    getStatusText(status) {
        const statusMap = {
            'connected': '已连接',
            'disconnected': '未连接',
            'disabled': '已禁用'
        };
        return statusMap[status] || status;
    }

    getInterfaceTypeText(type) {
        const typeMap = {
            'port': 'PORT',
            'lag': 'LAG'
        };
        return typeMap[type] || type.toUpperCase();
    }

    togglePort(portId) {
        // 端口控制功能暂时禁用 - 后端逻辑尚未实现
        console.warn(`端口控制功能暂不可用: ${portId}`);
        alert('端口控制功能正在开发中，敬请期待！');
        return false;
    }

    showLoading() {
        document.getElementById('loading').style.display = 'flex';
        document.getElementById('errorMessage').style.display = 'none';
        document.querySelector('.header-stats').style.display = 'none';
        document.querySelector('.port-visualization').style.display = 'none';
        document.querySelector('.port-table-container').style.display = 'none';
    }

    hideLoading() {
        document.getElementById('loading').style.display = 'none';
        document.querySelector('.header-stats').style.display = 'grid';
        document.querySelector('.port-visualization').style.display = 'block';
        document.querySelector('.port-table-container').style.display = 'block';
    }

    showError(message) {
        document.getElementById('loading').style.display = 'none';
        document.getElementById('errorMessage').style.display = 'flex';
        document.getElementById('errorText').textContent = message;
        document.querySelector('.header-stats').style.display = 'none';
        document.querySelector('.port-visualization').style.display = 'none';
        document.querySelector('.port-table-container').style.display = 'none';
    }

    startAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        
        if (this.autoRefreshEnabled) {
            this.refreshInterval = setInterval(() => {
                this.loadData();
            }, 30000); // 30秒刷新一次
        }
    }

    updateLastRefreshTime() {
        //更新最后刷新时间显示。
        const statusText = document.getElementById('statusText');
        if (statusText && this.lastUpdateTime) {
            const timeStr = this.lastUpdateTime.toLocaleTimeString();
            const originalText = statusText.textContent.split(' - ')[0];
            statusText.textContent = `${originalText} - ${timeStr}`;
        }
    }

    setupVisibilityHandling() {
        //设置页面可见性处理。
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                // 页面不可见时暂停自动刷新
                console.debug('页面不可见，暂停自动刷新');
                this.pauseAutoRefresh();
            } else {
                // 页面可见时恢复自动刷新
                console.debug('页面可见，恢复自动刷新');
                this.resumeAutoRefresh();
                // 立即刷新一次数据
                this.loadData();
            }
        });
    }

    pauseAutoRefresh() {
        //暂停自动刷新。
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    resumeAutoRefresh() {
        //恢复自动刷新。
        if (this.autoRefreshEnabled && !this.refreshInterval) {
            this.refreshInterval = setInterval(() => {
                this.loadData();
            }, 30000);
        }
    }

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    updateConnectionStatus(status, text) {
        const statusElement = document.getElementById('connectionStatus');
        const statusDot = document.getElementById('statusDot');
        const statusText = document.getElementById('statusText');

        if (statusElement && statusDot && statusText) {
            // 移除所有状态类
            statusElement.classList.remove('connected', 'error', 'mock', 'connecting');

            // 添加新状态类
            statusElement.classList.add(status);

            // 更新文本
            statusText.textContent = text;
        }
    }
}

// 初始化面板
let panel;
document.addEventListener('DOMContentLoaded', () => {
    panel = new EdgeSwitchPanel();
});

// 全局函数供 HTML 调用
function loadData() {
    if (panel) {
        panel.loadData();
    }
}
