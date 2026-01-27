const app = getApp();

Page({
  data: {
    events: [],
    total: 0,
    filter: 'all',
    loading: false,
    noMore: false,
    offset: 0,
    httpBase: ''
  },

  onLoad() {
    const httpBase = wx.getStorageSync('httpBase') || 'http://127.0.0.1:8000';
    this.setData({ httpBase });
    this.loadEvents();
  },

  onShow() {
    this.refresh();
  },

  loadEvents() {
    if (this.data.loading) return;
    this.setData({ loading: true });

    const { httpBase, offset, filter } = this.data;
    wx.request({
      url: `${httpBase}/api/events`,
      data: { limit: 20, offset },
      success: (res) => {
        if (res.data && res.data.events) {
          let events = res.data.events;

          // 过滤
          if (filter !== 'all') {
            events = events.filter(e => e.type === filter);
          }

          // 格式化时间
          events = events.map(e => {
            const time = e.time || {};
            const date = new Date(time.epoch_ms || Date.now());
            e.timeStr = date.toLocaleString('zh-CN', {
              month: '2-digit',
              day: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit'
            });
            return e;
          });

          const allEvents = offset === 0 ? events : this.data.events.concat(events);
          this.setData({
            events: allEvents,
            total: res.data.total || allEvents.length,
            noMore: events.length < 20
          });
        }
      },
      fail: (err) => {
        wx.showToast({ title: '加载失败', icon: 'none' });
      },
      complete: () => {
        this.setData({ loading: false });
      }
    });
  },

  refresh() {
    this.setData({ offset: 0, events: [], noMore: false });
    this.loadEvents();
  },

  loadMore() {
    if (this.data.noMore || this.data.loading) return;
    this.setData({ offset: this.data.offset + 20 });
    this.loadEvents();
  },

  setFilter(e) {
    const type = e.currentTarget.dataset.type;
    this.setData({ filter: type, offset: 0, events: [], noMore: false });
    this.loadEvents();
  },

  goDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/event-detail/event-detail?id=${id}`
    });
  }
});
