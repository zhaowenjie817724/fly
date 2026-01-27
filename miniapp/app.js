App({
  globalData: {
    httpBase: 'http://127.0.0.1:8000',
    wsUrl: 'ws://127.0.0.1:8000/ws',
    connected: false
  },

  onLaunch() {
    // 从缓存读取配置
    const httpBase = wx.getStorageSync('httpBase');
    const wsUrl = wx.getStorageSync('wsUrl');
    if (httpBase) this.globalData.httpBase = httpBase;
    if (wsUrl) this.globalData.wsUrl = wsUrl;
  },

  // 全局设置服务器地址
  setServer(httpBase, wsUrl) {
    this.globalData.httpBase = httpBase;
    this.globalData.wsUrl = wsUrl;
    wx.setStorageSync('httpBase', httpBase);
    wx.setStorageSync('wsUrl', wsUrl);
  }
})
