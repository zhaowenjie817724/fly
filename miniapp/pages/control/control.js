Page({
  data: {
    connected: false,
    fsmState: 'UNKNOWN',
    currentMode: '',
    roll: 0,
    pitch: 0,
    yaw: 0,
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
    wx.closeSocket();
  },

  connectWs() {
    const { wsUrl } = this.data;
    wx.connectSocket({ url: wsUrl });

    wx.onSocketOpen(() => {
      this.setData({ connected: true });
    });

    wx.onSocketClose(() => {
      this.setData({ connected: false });
      // 自动重连
      setTimeout(() => this.connectWs(), 3000);
    });

    wx.onSocketMessage((msg) => {
      try {
        const data = JSON.parse(msg.data);
        if (data.type === 'telemetry') {
          const payload = data.payload || {};
          const att = payload.attitude || {};
          this.setData({
            roll: (att.roll_deg || 0).toFixed(1),
            pitch: (att.pitch_deg || 0).toFixed(1),
            yaw: (att.yaw_deg || 0).toFixed(1)
          });
        }
        if (data.type === 'status') {
          const payload = data.payload || {};
          this.setData({
            connected: payload.link_status === 'OK'
          });
        }
      } catch (e) {}
    });
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

    const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

    wx.request({
      url: `${httpBase}${endpoint}`,
      method: 'POST',
      header: { 'content-type': 'application/json' },
      data: cmd === 'STOP' ? {} : params,
      success: (res) => {
        const success = res.data && res.data.accepted;
        this.addLog(time, `${cmd} ${JSON.stringify(params)}`, success);
        if (success) {
          wx.showToast({ title: '指令已发送', icon: 'success' });
        } else {
          wx.showToast({ title: res.data.error || '发送失败', icon: 'none' });
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

  // 急停长按确认
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
    // 同时切换到LOITER模式
    setTimeout(() => {
      this.sendCommand('SET_MODE', { mode: 'LOITER' });
      this.setData({ currentMode: 'LOITER', fsmState: 'EMERGENCY_STOP' });
    }, 200);
  },

  // 向后兼容：点击急停（提示长按）
  emergencyStop() {
    wx.showToast({
      title: '请长按以确认急停',
      icon: 'none',
      duration: 1500
    });
  }
});
