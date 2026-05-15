import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import WebSocketClient, { getWebSocketClient } from '../websocket';

describe('WebSocketClient', () => {
  let client: WebSocketClient;

  beforeEach(() => {
    client = new WebSocketClient('doctor-1');
  });

  afterEach(() => {
    client.disconnect();
  });

  it('should create instance', () => {
    expect(client).toBeDefined();
  });

  it('should register and call alert callback', () => {
    const callback = vi.fn();
    client.onAlert(callback);

    // 模拟触发回调
    (client as any).alertCallbacks.forEach((cb: Function) => cb({ id: 'alert-1' }));

    expect(callback).toHaveBeenCalledWith({ id: 'alert-1' });
  });

  it('should remove alert callback', () => {
    const callback = vi.fn();
    client.onAlert(callback);
    client.offAlert(callback);

    // 模拟触发回调
    (client as any).alertCallbacks.forEach((cb: Function) => cb({ id: 'alert-1' }));

    expect(callback).not.toHaveBeenCalled();
  });

  it('should register and call state change callback', () => {
    const callback = vi.fn();
    client.onStateChange(callback);

    // 模拟触发状态变化
    (client as any).notifyStateChange();

    expect(callback).toHaveBeenCalledWith('CLOSED');
  });

  it('should remove state change callback', () => {
    const callback = vi.fn();
    client.onStateChange(callback);
    client.offStateChange(callback);

    // 模拟触发状态变化
    (client as any).notifyStateChange();

    expect(callback).not.toHaveBeenCalled();
  });

  it('should return connection state', () => {
    expect(client.getConnectionState()).toBe('CLOSED');
  });
});

describe('getWebSocketClient', () => {
  it('should return singleton instance', () => {
    const client1 = getWebSocketClient('doctor-1');
    const client2 = getWebSocketClient('doctor-1');
    expect(client1).toBe(client2);
  });
});
