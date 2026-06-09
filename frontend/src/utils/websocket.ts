/**
 * 通用 WebSocket 客户端管理器
 * 支持医生端和护士端的实时预警推送
 */

type AlertCallback = (alert: any) => void;
type AlertStatusChangeCallback = (alert: any) => void;
type StateChangeCallback = (state: string) => void;

export type WSRole = 'doctor' | 'nurse';

class WebSocketClient {
  private ws: WebSocket | null = null;
  private userId: string;
  private role: WSRole;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectInterval = 3000;
  private alertCallbacks: AlertCallback[] = [];
  private alertStatusChangeCallbacks: AlertStatusChangeCallback[] = [];
  private stateChangeCallbacks: StateChangeCallback[] = [];
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private intentionalClose = false;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

  constructor(userId: string, role: WSRole = 'doctor') {
    this.userId = userId;
    this.role = role;
  }

  connect(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    if (this.ws) {
      this.stopHeartbeat();
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }

    this.intentionalClose = false;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const path = this.role === 'nurse'
      ? `/ws/nurse-alerts/${this.userId}`
      : `/ws/alerts/${this.userId}`;
    const token = localStorage.getItem('token') || '';
    const wsUrl = `${protocol}//${window.location.host}${path}?token=${encodeURIComponent(token)}`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log(`[${this.role}] WebSocket 连接成功`);
        this.reconnectAttempts = 0;
        this.startHeartbeat();
        this.notifyStateChange();
      };

      this.ws.onmessage = (event) => {
        // 跳过心跳响应
        if (event.data === 'pong') return;

        try {
          const data = JSON.parse(event.data);
          if (data.type === 'NEW_ALERT') {
            this.alertCallbacks.forEach(callback => callback(data.data));
          } else if (data.type === 'ALERT_STATUS_CHANGE') {
            this.alertStatusChangeCallbacks.forEach(callback => callback(data.data));
          }
        } catch (error) {
          console.error('解析 WebSocket 消息失败:', error);
        }
      };

      this.ws.onclose = (event) => {
        console.log(`[${this.role}] WebSocket 连接关闭:`, event.code, event.reason);
        this.stopHeartbeat();
        this.notifyStateChange();
        if (!this.intentionalClose) {
          this.attemptReconnect();
        }
      };

      this.ws.onerror = (error) => {
        console.error(`[${this.role}] WebSocket 错误:`, error);
      };
    } catch (error) {
      console.error('创建 WebSocket 连接失败:', error);
      this.attemptReconnect();
    }
  }

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

  private attemptReconnect(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`[${this.role}] 尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
      this.reconnectTimeout = setTimeout(() => {
        this.connect();
      }, this.reconnectInterval);
    } else {
      console.error(`[${this.role}] 达到最大重连次数，停止重连`);
    }
  }

  private startHeartbeat(): void {
    this.heartbeatInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send('ping');
      }
    }, 30000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  onAlert(callback: AlertCallback): void {
    this.alertCallbacks.push(callback);
  }

  offAlert(callback: AlertCallback): void {
    this.alertCallbacks = this.alertCallbacks.filter(cb => cb !== callback);
  }

  onAlertStatusChange(callback: AlertStatusChangeCallback): void {
    this.alertStatusChangeCallbacks.push(callback);
  }

  offAlertStatusChange(callback: AlertStatusChangeCallback): void {
    this.alertStatusChangeCallbacks = this.alertStatusChangeCallbacks.filter(cb => cb !== callback);
  }

  onStateChange(callback: StateChangeCallback): void {
    this.stateChangeCallbacks.push(callback);
  }

  offStateChange(callback: StateChangeCallback): void {
    this.stateChangeCallbacks = this.stateChangeCallbacks.filter(cb => cb !== callback);
  }

  private notifyStateChange(): void {
    const state = this.getConnectionState();
    this.stateChangeCallbacks.forEach(cb => cb(state));
  }

  getConnectionState(): string {
    if (!this.ws) return 'CLOSED';
    switch (this.ws.readyState) {
      case WebSocket.CONNECTING: return 'CONNECTING';
      case WebSocket.OPEN: return 'OPEN';
      case WebSocket.CLOSING: return 'CLOSING';
      case WebSocket.CLOSED: return 'CLOSED';
      default: return 'UNKNOWN';
    }
  }

  getUserId(): string { return this.userId; }
  getRole(): WSRole { return this.role; }
}

// 医生端单例
let doctorWsClient: WebSocketClient | null = null;

export function getWebSocketClient(doctorId: string): WebSocketClient {
  if (!doctorWsClient) {
    doctorWsClient = new WebSocketClient(doctorId, 'doctor');
  } else if (doctorWsClient.getUserId() !== doctorId) {
    doctorWsClient.disconnect();
    doctorWsClient = new WebSocketClient(doctorId, 'doctor');
  }
  return doctorWsClient;
}

// 护士端单例
let nurseWsClient: WebSocketClient | null = null;

export function getNurseWebSocketClient(nurseId: string): WebSocketClient {
  if (!nurseWsClient) {
    nurseWsClient = new WebSocketClient(nurseId, 'nurse');
  } else if (nurseWsClient.getUserId() !== nurseId) {
    nurseWsClient.disconnect();
    nurseWsClient = new WebSocketClient(nurseId, 'nurse');
  }
  return nurseWsClient;
}

export default WebSocketClient;
