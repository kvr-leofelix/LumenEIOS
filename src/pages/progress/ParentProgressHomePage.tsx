import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardBody, CardHeader } from '../../components/common/Card';
import { apiClient } from '../../lib/apiClient';
import { useAuth } from '../../context/AuthContext';
import { UnauthorizedPage } from '../shared/UnauthorizedPage';
import { ProgressEmpty, ProgressError, ProgressLoading } from './components/ProgressStates';

type LinkedChild = {
  id: string;
  name?: string;
  class_name?: string;
  className?: string;
  roll_no?: number;
  rollNo?: number;
};

export const ParentProgressHomePage: React.FC = () => {
  const { currentUser } = useAuth();
  const [children, setChildren] = useState<LinkedChild[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (currentUser?.role !== 'parent') return;
    setLoading(true);
    apiClient.homework
      .parentChildren()
      .then((rows) => setChildren(Array.isArray(rows) ? rows : []))
      .catch(setError)
      .finally(() => setLoading(false));
  }, [currentUser?.role]);

  if (currentUser?.role !== 'parent') return <UnauthorizedPage />;
  if (loading) return <ProgressLoading label="Loading linked students…" />;
  if (error) return <ProgressError error={error} />;

  return (
    <div className="space-y-6">
      <div className="bg-white p-5 rounded-2xl border border-surface-border shadow-subtle">
        <h1 className="text-xl font-bold text-navy-900 tracking-tight">Unified Student Progress</h1>
        <p className="text-xs text-content-secondary mt-1">
          Choose a linked child to view verified competency and longitudinal progress.
        </p>
      </div>

      <Card>
        <CardHeader title="Linked students" subtitle="Visibility follows the same parent–child links as homework." />
        <CardBody>
          {!children.length ? (
            <ProgressEmpty
              title="No linked students"
              detail="Ask the school to link your guardian account to a student before progress can be shown."
            />
          ) : (
            <ul className="space-y-2.5">
              {children.map((child) => (
                <li key={child.id}>
                  <Link
                    to={`/parent/students/${encodeURIComponent(child.id)}/progress`}
                    className="block p-3.5 rounded-xl border border-surface-border hover:border-teal-400 hover:bg-teal-50/40 transition-colors"
                  >
                    <p className="text-sm font-semibold text-navy-900">{child.name || child.id}</p>
                    <p className="text-[11px] text-content-secondary mt-0.5">
                      {child.class_name || child.className || 'Class unavailable'}
                      {child.roll_no != null || child.rollNo != null
                        ? ` · Roll #${child.roll_no ?? child.rollNo}`
                        : ''}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
};
