const DEFAULT_WS = "ws://127.0.0.1:8000/ws";
const DEFAULT_HTTP = "http://127.0.0.1:8000/command";

Page({
  data: {
    connected: false,
    wsUrl: DEFAULT_WS,
    httpUrl: DEFAULT_HTTP,
    telemetry: {
      battery_v: "",
      battery_pct: "",
      attitude: "",
      gps: "",
      alt: ""
    },
    status: {
      gcsLabel: "地面站",
      linkText: "未知",
      lastUpdate: "-"
    },
    events: [],
    observations: []
  },

  onLoad() {
    const wsUrl = wx.getStorageSync("wsUrl") || DEFAULT_WS;
    const httpUrl = wx.getStorageSync("httpUrl") || DEFAULT_HTTP;
    this.setData({ wsUrl, httpUrl });
    this.connect();
  },

  connect() {
    if (this.connecting) {
      return;
    }
    this.connecting = true;
    const wsUrl = this.data.wsUrl;
    wx.connectSocket({ url: wsUrl });

    wx.onSocketOpen(() => {
      this.setData({ connected: true });
      this.retries = 0;
      this.connecting = false;
    });

    wx.onSocketClose(() => {
      this.setData({ connected: false });
      this.connecting = false;
      this.scheduleReconnect();
    });

    wx.onSocketMessage((msg) => {
      try {
        const data = JSON.parse(msg.data);
        if (data.type === "telemetry") {
          const payload = data.payload || {};
          this.setData({
            telemetry: {
              battery_v: payload.battery ? payload.battery.voltage_v : "",
              battery_pct: payload.battery ? payload.battery.remaining_pct : "",
              attitude: payload.attitude
                ? `${payload.attitude.roll_deg.toFixed(1)},${payload.attitude.pitch_deg.toFixed(1)},${payload.attitude.yaw_deg.toFixed(1)}`
                : "",
              gps: payload.gps ? `${payload.gps.lat.toFixed(5)},${payload.gps.lon.toFixed(5)}` : "",
              alt: payload.gps ? payload.gps.alt_m.toFixed(1) : ""
            }
          });
        }
        if (data.type === "event") {
          const events = [data.payload].concat(this.data.events);
          this.setData({ events: events.slice(0, 20) });
        }
        if (data.type && data.type.indexOf("observation:") === 0) {
          const payload = data.payload || {};
          const desc = payload.bearing_deg !== null && payload.bearing_deg !== undefined
            ? `方位 ${payload.bearing_deg.toFixed(1)}° 置信 ${payload.confidence}`
            : payload.status;
          const observations = [{ source: payload.source, desc }].concat(this.data.observations);
          this.setData({ observations: observations.slice(0, 20) });
        }
        if (data.type === "status") {
          const payload = data.payload || {};
          const linkMap = {
            OK: "正常",
            DEGRADED: "降级",
            LOST: "断开",
            UNKNOWN: "未知"
          };
          const epoch = payload.last_telemetry_epoch_ms;
          const lastUpdate = epoch ? new Date(epoch).toLocaleTimeString() : "-";
          this.setData({
            status: {
              gcsLabel: payload.gcs_label || "地面站",
              linkText: linkMap[payload.link_status] || payload.link_status || "未知",
              lastUpdate
            }
          });
        }
      } catch (err) {
        // Ignore parse errors
      }
    });
  },

  scheduleReconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    const retry = this.retries || 0;
    const delay = Math.min(10000, 1000 * Math.pow(2, retry));
    this.retries = retry + 1;
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  },

  reconnect() {
    wx.closeSocket();
    this.connect();
  },

  onWsInput(e) {
    const wsUrl = e.detail.value;
    this.setData({ wsUrl });
    wx.setStorageSync("wsUrl", wsUrl);
  },

  onHttpInput(e) {
    const httpUrl = e.detail.value;
    this.setData({ httpUrl });
    wx.setStorageSync("httpUrl", httpUrl);
  },

  sendCommand(payload) {
    wx.request({
      url: this.data.httpUrl,
      method: "POST",
      header: {
        "content-type": "application/json"
      },
      data: payload
    });
  },

  yawLeft() {
    this.sendCommand({
      type: "SET_YAW",
      params: { yaw_deg: -10, duration_ms: 500 }
    });
  },

  yawRight() {
    this.sendCommand({
      type: "SET_YAW",
      params: { yaw_deg: 10, duration_ms: 500 }
    });
  },

  setLoiter() {
    this.sendCommand({
      type: "SET_MODE",
      params: { mode: "LOITER" }
    });
  },

  stop() {
    this.sendCommand({ type: "STOP", params: {} });
  }
});
