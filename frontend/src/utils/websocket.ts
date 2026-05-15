/**
 * WebSocket 客户端管理器
 * 用于接收实时预警推送
 */

type AlertCallback = (alert: any) => void;

class WebSocketClient {
  private ws: WebSocket | null = null;
  private doctorId: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectInterval = 3000; // 3秒
  private alertCallbacks: AlertCallback[] = [];
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private intentionalClose = false;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

  constructor(doctorId: string) {
    this.doctorId = doctorId;
  }

  /**
   * 连接 WebSocket
   */
  connect(): void {
    // 如果已连接，先断开
    if (this.ws) {
      this.disconnect();
    }

    this.intentionalClose = false;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/alerts/${this.doctorId}`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('WebSocket 连接成功');
        this.reconnectAttempts = 0;
        this.startHeartbeat();
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'NEW_ALERT') {
            // 触发所有注册的回调
            this.alertCallbacks.forEach(callback => callback(data.data));
          }
        } catch (error) {
          console.error('解析 WebSocket 消息失败:', error);
        }
      };

      this.ws.onclose = (event) => {
        console.log('WebSocket 连接关闭:', event.code, event.reason);
        this.stopHeartbeat();
        if (!this.intentionalClose) {
          this.attemptReconnect();
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket 错误:', error);
      };
    } catch (error) {
      console.error('创建 WebSocket 连接失败:', error);
      this.attemptReconnect();
    }
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    this.intentionalClose = true;
    this.stopHeartbeat();
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  /**
   * 尝试重连
   */
  private attemptReconnect(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);

      this.reconnectTimeout = setTimeout(() => {
        this.connect();
      }, this.reconnectInterval);
    } else {
      console.error('达到最大重连次数，停止重连');
    }
  }

  /**
   * 开始心跳
   */
  private startHeartbeat(): void {
    this.heartbeatInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send('ping');
      }
    }, 30000); // 每30秒发送心跳
  }

  /**
   * 停止心跳
   */
  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  /**
   * 注册预警回调
   */
  onAlert(callback: AlertCallback): void {
    this.alertCallbacks.push(callback);
  }

  /**
   * 移除预警回调
   */
  offAlert(callback: AlertCallback): void {
    this.alertCallbacks = this.alertCallbacks.filter(cb => cb !== callback);
  }

  /**
   * 获取连接状态
   */
  getConnectionState(): string {
    if (!this.ws) return 'CLOSED';

    switch (this.ws.readyState) {
      case WebSocket.CONNECTING:
        return 'CONNECTING';
      case WebSocket.OPEN:
        return 'OPEN';
      case WebSocket.CLOSING:
        return 'CLOSING';
      case WebSocket.CLOSED:
        return 'CLOSED';
      default:
        return 'UNKNOWN';
    }
  }

  /**
   * 获取 doctorId
   */
  getDoctorId(): string {
    return this.doctorId;
  }
}

// 创建单例实例
let wsClient: WebSocketClient | null = null;

/**
 * 获取 WebSocket 客户端实例
 */
export function getWebSocketClient(doctorId: string): WebSocketClient {
  if (!wsClient) {
    wsClient = new WebSocketClient(doctorId);
  } else if (wsClient.getDoctorId() !== doctorId) {
    // 如果 doctorId 变化，断开旧连接并创建新实例
    wsClient.disconnect();
    wsClient = new WebSocketClient(doctorId);
  }
  return wsClient;
}

export default WebSocketClient;
