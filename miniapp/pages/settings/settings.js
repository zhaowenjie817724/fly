const app = getApp();

Page({
  data: {
    httpBase: '',
    wsUrl: '',
    connOk: false,
    connMsg: '未测试',
    serverStatus: '-',
    runDir: '',
    linkStatus: '',
    fsmState: ''
  },

  onLoad() {
    const httpBase = wx.getStorageSync('httpBase') || app.globalData.httpBase;
    const wsUrl = wx.getStorageSync('wsUrl') || app.globalData.wsUrl;
    this.setData({ httpBase, wsUrl });
  },

  onShow() {
    this.fetchStatus();
  },

  onHttpInput(e) {
    this.setData({ httpBase: e.detail.value });
  },

  onWsInput(e) {
    this.setData({ wsUrl: e.detail.value });
  },

  applyPreset(e) {
    const host = e.currentTarget.dataset.host;
    const httpBase = `http://${host}:8000`;
    const wsUrl = `ws://${host}:8000/ws`;
    this.setData({ httpBase, wsUrl });
    this.saveServer();
  },

  saveServer() {
    const { httpBase, wsUrl } = this.data;
    app.setServer(httpBase, wsUrl);
    wx.showToast({ title: '已保存', icon: 'success' });
    this.testConnection();
  },

  testConnection() {
    const { httpBase } = this.data;
    this.setData({ connMsg: '测试中...' });
    wx.request({
      url: `${httpBase}/health`,
      timeout: 5000,
      success: (res) => {
        if (res.data && res.data.status === 'ok') {
          this.setData({ connOk: true, connMsg: '连接成功' });
          this.fetchStatus();
        } else {
          this.setData({ connOk: false, connMsg: '响应异常' });
        }
      },
      fail: () => {
        this.setData({ connOk: false, connMsg: '连接失败' });
      }
    });
  },

  fetchStatus() {
    const { httpBase } = this.data;
    wx.request({
      url: `${httpBase}/status`,
      success: (res) => {
        if (res.data) {
          this.setData({
            serverStatus: 'OK',
            runDir: res.data.run_dir || '-',
            linkStatus: res.data.link_status || '-'
          });
        }
      }
    });
    wx.request({
      url: `${httpBase}/api/fsm`,
      success: (res) => {
        if (res.data) {
          this.setData({ fsmState: res.data.fsm_state || '-' });
        }
      }
    });
  }
});
