type FrameListener = (payload: { encoding: string; data: string }) => void;

const listeners = new Map<string, Set<FrameListener>>();

export function publishFrame(boxId: string, payload: { encoding: string; data: string }) {
  listeners.get(boxId)?.forEach((listener) => listener(payload));
}

export function subscribeFrame(boxId: string, listener: FrameListener) {
  const boxListeners = listeners.get(boxId) ?? new Set<FrameListener>();
  boxListeners.add(listener);
  listeners.set(boxId, boxListeners);
  return () => {
    boxListeners.delete(listener);
    if (boxListeners.size === 0) listeners.delete(boxId);
  };
}
