const app = getApp();

Page({
  data: {
    connected: false,
    fsmState: 'UNKNOWN',
    currentMode: '',
    roll: '0.0',
    pitch: '0.0',
    yaw: '0.0',
    // 视觉
    bearing: '--',
    obsConf: '--',
    obsStatus: 'NO_SIGNAL',
    // 热成像
    thermalBearing: '--',
    thermalConf: '--',
    thermalStatus: 'NO_SIGNAL',
    // 声源 DOA
    doaBearing: '--',
    doaConf: '--',
    doaStatus: 'NO_SIGNAL',
    // 三路融合结果
    fusedBearing: '--',
    fusedConf: '--',
    fusedStatus: 'NO_SIGNAL',
    fusedSources: '无信号',
    // 其他
    cmdLogs: [],
    httpBase: '',
    wsUrl: ''
  },

  onLoad() {
    const httpBase = wx.getStorageSync('httpBase') || 'http://127.0.0.1:8000';
    const wsUrl = wx.getStorageSync('wsUrl') || 'ws://127.0.0.1:8000/ws';
    this.setData({ httpBase, wsUrl });
    this.connectWs();
    this.loadFsmState();
  },

  onUnload() {
    if (this._socket) {
      this._socket.close({});
      this._socket = null;
    }
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
    }
  },

  connectWs() {
    if (this._socket) {
      this._socket.close({});
      this._socket = null;
    }
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }

    const { wsUrl } = this.data;
    const socket = wx.connectSocket({ url: wsUrl });
    this._socket = socket;

    socket.onOpen(() => {
      this.setData({ connected: true });
    });

    socket.onClose(() => {
      this.setData({ connected: false });
      this._socket = null;
      this._reconnectTimer = setTimeout(() => this.connectWs(), 3000);
    });

    socket.onError(() => {
      this.setData({ connected: false });
    });

    socket.onMessage((msg) => {
      try {
        const data = JSON.parse(msg.data);
        this._handleWsMessage(data, socket);
      } catch (e) {}
    });
  },

  _handleWsMessage(data, socket) {
    const type = data.type || '';

    // 心跳响应
    if (type === 'ping') {
      socket.send({ data: JSON.stringify({ type: 'pong', payload: data.payload }) });
      return;
    }

    // 遥测姿态
    if (type === 'telemetry') {
      const payload = data.payload || {};
      const att = payload.attitude || {};
      this.setData({
        roll: (att.roll_deg || 0).toFixed(1),
        pitch: (att.pitch_deg || 0).toFixed(1),
        yaw: (att.yaw_deg || 0).toFixed(1)
      });
    }

    // 链路状态
    if (type === 'status') {
      const payload = data.payload || {};
      const linkOk = payload.link_status === 'OK';
      this.setData({ connected: linkOk });
    }

    // 观测数据：根据 stem（文件名）分流处理
    if (type.startsWith('observation:')) {
      const stem = type.slice('observation:'.length);
      const payload = data.payload || {};
      this._updateSensor(stem, payload);
    }
  },

  _updateSensor(stem, payload) {
    const status = payload.status || 'NO_SIGNAL';
    const hasSignal = status === 'OK' && payload.bearing_deg != null;
    const bearingStr = hasSignal ? payload.bearing_deg.toFixed(1) : '--';
    const confStr = hasSignal ? ((payload.confidence || 0) * 100).toFixed(0) + '%' : '--';

    if (stem === 'vision_yolo') {
      this.setData({
        bearing: bearingStr,
        obsConf: confStr,
        obsStatus: status
      });
    } else if (stem === 'thermal_obs') {
      this.setData({
        thermalBearing: bearingStr,
        thermalConf: confStr,
        thermalStatus: status
      });
    } else if (stem === 'doa_obs') {
      this.setData({
        doaBearing: bearingStr,
        doaConf: confStr,
        doaStatus: status
      });
    } else if (stem === 'fused') {
      const sources = (payload.extras && payload.extras.sources) || [];
      const labelMap = { vision: '视觉', thermal: '热成像', audio: '声源' };
      const sourceStr = sources.length
        ? sources.map(s => labelMap[s] || s).join('+')
        : '无信号';
      this.setData({
        fusedBearing: bearingStr,
        fusedConf: confStr,
        fusedStatus: status,
        fusedSources: sourceStr
      });
    }
    // observations.jsonl（vision_live 模式）也响应方位显示
    else if (stem === 'observations') {
      this.setData({
        bearing: bearingStr,
        obsConf: confStr,
        obsStatus: status
      });
    }
  },

  loadFsmState() {
    const { httpBase } = this.data;
    wx.request({
      url: `${httpBase}/api/fsm`,
      success: (res) => {
        if (res.data && res.data.fsm_state) {
          this.setData({ fsmState: res.data.fsm_state });
        }
      }
    });
  },

  sendCommand(cmd, params = {}) {
    const { httpBase } = this.data;
    const endpoint = cmd === 'SET_YAW' ? '/api/control/yaw' :
                     cmd === 'SET_MODE' ? '/api/control/mode' :
                     cmd === 'STOP' ? '/api/control/estop' : '/command';

    const time = new Date().toLocaleTimeString('zh-CN', {
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    });

    wx.request({
      url: `${httpBase}${endpoint}`,
      method: 'POST',
      header: { 'content-type': 'application/json' },
      data: cmd === 'STOP' ? {} : params,
      success: (res) => {
        const success = !!(res.data && res.data.accepted);
        this.addLog(time, `${cmd} ${JSON.stringify(params)}`, success);
        if (success) {
          wx.showToast({ title: '指令已发送', icon: 'success' });
        } else {
          wx.showToast({ title: (res.data && res.data.error) || '发送失败', icon: 'none' });
        }
      },
      fail: () => {
        this.addLog(time, `${cmd} ${JSON.stringify(params)}`, false);
        wx.showToast({ title: '网络错误', icon: 'none' });
      }
    });
  },

  addLog(time, cmd, success) {
    const logs = [{ time, cmd, success }].concat(this.data.cmdLogs).slice(0, 10);
    this.setData({ cmdLogs: logs });
  },

  yawLeft(e) {
    const deg = parseInt(e.currentTarget.dataset.deg) || 10;
    this.sendCommand('SET_YAW', { yaw_deg: -deg });
  },

  yawRight(e) {
    const deg = parseInt(e.currentTarget.dataset.deg) || 10;
    this.sendCommand('SET_YAW', { yaw_deg: deg });
  },

  setMode(e) {
    const mode = e.currentTarget.dataset.mode;
    this.sendCommand('SET_MODE', { mode });
    this.setData({ currentMode: mode });
  },

  onEstopLongPress() {
    wx.vibrateShort({ type: 'heavy' });
    wx.showModal({
      title: '确认急停',
      content: '将立即停止所有运动并切换到悬停模式，确定执行？',
      confirmText: '确认急停',
      confirmColor: '#ef4444',
      success: (res) => {
        if (res.confirm) {
          this.executeEstop();
        }
      }
    });
  },

  executeEstop() {
    wx.vibrateShort({ type: 'heavy' });
    this.sendCommand('STOP');
    setTimeout(() => {
      this.sendCommand('SET_MODE', { mode: 'LOITER' });
      this.setData({ currentMode: 'LOITER', fsmState: 'EMERGENCY_STOP' });
    }, 200);
  },

  emergencyStop() {
    wx.showToast({ title: '请长按以确认急停', icon: 'none', duration: 1500 });
  }
});
