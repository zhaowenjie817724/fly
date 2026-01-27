Page({
  data: {
    event: null,
    timeStr: '',
    refJson: '',
    httpBase: ''
  },

  onLoad(options) {
    const httpBase = wx.getStorageSync('httpBase') || 'http://127.0.0.1:8000';
    this.setData({ httpBase });

    if (options.id) {
      this.loadEvent(options.id);
    }
  },

  loadEvent(id) {
    const { httpBase } = this.data;
    wx.request({
      url: `${httpBase}/api/events/${id}`,
      success: (res) => {
        if (res.data && !res.data.error) {
          const event = res.data;
          const time = event.time || {};
          const date = new Date(time.epoch_ms || Date.now());
          const timeStr = date.toLocaleString('zh-CN');
          const refJson = event.ref ? JSON.stringify(event.ref, null, 2) : '';

          this.setData({ event, timeStr, refJson });
        } else {
          wx.showToast({ title: '事件不存在', icon: 'none' });
        }
      },
      fail: () => {
        wx.showToast({ title: '加载失败', icon: 'none' });
      }
    });
  },

  previewImage() {
    const { httpBase, event } = this.data;
    if (event && event.snapshot) {
      wx.previewImage({
        urls: [`${httpBase}${event.snapshot}`]
      });
    }
  },

  goBack() {
    wx.navigateBack();
  }
});
