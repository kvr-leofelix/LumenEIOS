import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { describeError } from '../../lib/teacherPlanApi';

/** Loads backend data and reloads when the active school changes. Errors are surfaced, never swallowed. */
export function useRemote<T>(load: () => Promise<T>, deps: unknown[]) {
  const { currentSchoolId } = useAuth();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const latest = useRef(0);
  const run = useCallback(() => {
    // Ignore responses from superseded requests (e.g. the identity changed while an earlier load was in flight).
    const id = ++latest.current;
    const current = () => id === latest.current;
    setLoading(true);
    setError('');
    Promise.resolve()
      .then(load)
      .then((value) => { if (current()) setData(value); })
      .catch((e) => {
        if (!current()) return;
        setData(null);
        setError(describeError(e).message);
      })
      .finally(() => { if (current()) setLoading(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSchoolId, ...deps]);
  useEffect(run, [run]);
  return { data, error, loading, reload: run };
}
