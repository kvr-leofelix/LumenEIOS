import { useCallback, useEffect, useRef, useState } from 'react';

export type AsyncState<T> =
  | { status: 'loading'; data: null; error: null }
  | { status: 'success'; data: T; error: null }
  | { status: 'error'; data: null; error: unknown };

/** Runs an async loader, ignoring stale responses when dependencies change. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<AsyncState<T>>({ status: 'loading', data: null, error: null });
  const requestId = useRef(0);

  const run = useCallback(() => {
    const id = ++requestId.current;
    setState({ status: 'loading', data: null, error: null });
    loader().then(
      (data) => id === requestId.current && setState({ status: 'success', data, error: null }),
      (error) => id === requestId.current && setState({ status: 'error', data: null, error })
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    run();
  }, [run]);

  const setData = useCallback((updater: (prev: T) => T) => {
    setState((s) => (s.status === 'success' ? { ...s, data: updater(s.data) } : s));
  }, []);

  return { ...state, reload: run, setData };
}
