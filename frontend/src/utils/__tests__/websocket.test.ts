import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import WebSocketClient, { getWebSocketClient, getNurseWebSocketClient } from '../websocket';

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

  it('should default to doctor role', () => {
    expect(client.getRole()).toBe('doctor');
    expect(client.getUserId()).toBe('doctor-1');
  });

  it('should register and call alert callback', () => {
    const callback = vi.fn();
    client.onAlert(callback);

    (client as any).alertCallbacks.forEach((cb: Function) => cb({ id: 'alert-1' }));

    expect(callback).toHaveBeenCalledWith({ id: 'alert-1' });
  });

  it('should remove alert callback', () => {
    const callback = vi.fn();
    client.onAlert(callback);
    client.offAlert(callback);

    (client as any).alertCallbacks.forEach((cb: Function) => cb({ id: 'alert-1' }));

    expect(callback).not.toHaveBeenCalled();
  });

  it('should register and call state change callback', () => {
    const callback = vi.fn();
    client.onStateChange(callback);

    (client as any).notifyStateChange();

    expect(callback).toHaveBeenCalledWith('CLOSED');
  });

  it('should remove state change callback', () => {
    const callback = vi.fn();
    client.onStateChange(callback);
    client.offStateChange(callback);

    (client as any).notifyStateChange();

    expect(callback).not.toHaveBeenCalled();
  });

  it('should return connection state', () => {
    expect(client.getConnectionState()).toBe('CLOSED');
  });
});

describe('WebSocketClient - Nurse', () => {
  let client: WebSocketClient;

  beforeEach(() => {
    client = new WebSocketClient('nurse-1', 'nurse');
  });

  afterEach(() => {
    client.disconnect();
  });

  it('should create nurse instance with nurse role', () => {
    expect(client).toBeDefined();
    expect(client.getRole()).toBe('nurse');
    expect(client.getUserId()).toBe('nurse-1');
  });

  it('should register and call alert callback', () => {
    const callback = vi.fn();
    client.onAlert(callback);

    (client as any).alertCallbacks.forEach((cb: Function) => cb({ id: 'alert-nurse-1' }));

    expect(callback).toHaveBeenCalledWith({ id: 'alert-nurse-1' });
  });

  it('should return CLOSED state when not connected', () => {
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

describe('getNurseWebSocketClient', () => {
  it('should return singleton instance', () => {
    const client1 = getNurseWebSocketClient('nurse-1');
    const client2 = getNurseWebSocketClient('nurse-1');
    expect(client1).toBe(client2);
  });

  it('should have nurse role', () => {
    const client = getNurseWebSocketClient('nurse-1');
    expect(client.getRole()).toBe('nurse');
  });
});
