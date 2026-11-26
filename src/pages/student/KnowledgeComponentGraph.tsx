import React, { useEffect, useMemo, useState } from 'react';
import { ApiError, apiClient } from '../../lib/apiClient';
import { Card, CardHeader, CardBody } from '../../components/common/Card';

export type LearningStatus = 'proficient' | 'developing' | 'needs_improvement' | 'not_assessed';

export type KnowledgeGraph = Awaited<ReturnType<typeof apiClient.knowledgeGraph.mine>>;
export type KnowledgeGraphNode = KnowledgeGraph['nodes'][number];

const STATUS_STYLE: Record<LearningStatus, { dot: string; border: string; label: string }> = {
  proficient: { dot: 'bg-emerald-500', border: 'border-emerald-600', label: 'Proficient' },
  developing: { dot: 'bg-amber-400', border: 'border-amber-500', label: 'Developing' },
  needs_improvement: { dot: 'bg-red-500', border: 'border-red-600', label: 'Needs Improvement' },
  not_assessed: { dot: 'bg-gray-400', border: 'border-gray-400', label: 'Not Assessed' },
};

function scoreText(value: number | null) {
  return value == null ? 'Not assessed' : `${value}%`;
}

function layout(graph: KnowledgeGraph) {
  const rank = new Map<string, number>();
  graph.nodes.forEach((node) => rank.set(node.id, 0));
  const prerequisite = graph.edges.filter((edge) => edge.relationship === 'PREREQUISITE_OF');
  for (let pass = 0; pass < graph.nodes.length; pass += 1) {
    prerequisite.forEach((edge) => {
      const next = (rank.get(edge.source_id) ?? 0) + 1;
      if (next > (rank.get(edge.target_id) ?? 0)) rank.set(edge.target_id, next);
    });
  }
  const columns = new Map<number, KnowledgeGraphNode[]>();
  graph.nodes.forEach((node) => {
    const column = rank.get(node.id) ?? 0;
    columns.set(column, [...(columns.get(column) ?? []), node]);
  });
  const ordered = [...columns.keys()].sort((a, b) => a - b);
  const positions = new Map<string, { x: number; y: number }>();
  ordered.forEach((column, columnIndex) => {
    (columns.get(column) ?? []).forEach((node, row) => {
      positions.set(node.id, { x: 28 + columnIndex * 190, y: 20 + row * 78 });
    });
  });
  const width = Math.max(280, ordered.length * 190 + 20);
  const height = Math.max(96, Math.max(0, ...[...columns.values()].map((items) => items.length)) * 78 + 16);
  return { positions, width, height };
}

export function KnowledgeGraphView({ graph }: { graph: KnowledgeGraph }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const placed = useMemo(() => layout(graph), [graph]);
  const selected = graph.nodes.find((node) => node.id === selectedId) ?? null;

  if (graph.nodes.length === 0) {
    return (
      <p className="text-sm text-content-secondary">
        No concept has been assessed from your evaluated work yet. Your teacher adds the concepts for the subject, then evaluates a scan of your work.
      </p>
    );
  }

  const assessed = graph.nodes.filter((node) => node.learning_status !== 'not_assessed');

  return (
    <div className="space-y-4">
      {assessed.length > 0 && (
        <ul className="grid gap-2 sm:grid-cols-2">
          {assessed.map((node) => {
            const style = STATUS_STYLE[node.learning_status];
            return (
              <li key={node.id} className="flex items-center justify-between rounded-lg border border-surface-border bg-white px-3 py-2 text-xs">
                <span className="flex items-center gap-1.5 font-semibold text-navy-900">
                  <span className={`h-2.5 w-2.5 rounded-full ${style.dot}`} />
                  {node.name}
                </span>
                <span className="text-content-secondary">{style.label} · {node.overall_mastery}%</span>
              </li>
            );
          })}
        </ul>
      )}
      {graph.insights.length > 0 && (
        <ul className="space-y-1 text-xs text-navy-900">
          {graph.insights.map((insight) => <li key={insight}>{insight}</li>)}
        </ul>
      )}
      <div className="overflow-auto rounded-xl border border-surface-border bg-surface-bg/40">
        <div className="relative" style={{ width: placed.width, height: placed.height }}>
          <svg className="absolute left-0 top-0" width={placed.width} height={placed.height} role="img" aria-label="Knowledge component graph">
          {graph.edges.map((edge) => {
            const from = placed.positions.get(edge.source_id);
            const to = placed.positions.get(edge.target_id);
            if (!from || !to) return null;
            return (
              <line
                key={`${edge.source_id}-${edge.relationship}-${edge.target_id}`}
                x1={from.x + 70}
                y1={from.y + 24}
                x2={to.x + 70}
                y2={to.y + 24}
                stroke={edge.relationship === 'RELATED_TO' ? '#94a3b8' : '#0f766e'}
                strokeDasharray={edge.relationship === 'RELATED_TO' ? '4 3' : undefined}
                strokeWidth="1.5"
              />
            );
          })}
        </svg>
        {graph.nodes.map((node) => {
          const style = STATUS_STYLE[node.learning_status];
          const position = placed.positions.get(node.id);
          if (!position) return null;
          return (
            <button
              key={node.id}
              type="button"
              data-status={node.learning_status}
              aria-pressed={selectedId === node.id}
              onClick={() => setSelectedId(node.id)}
              className={`absolute z-10 w-36 rounded-lg border bg-white px-2 py-1.5 text-left shadow-subtle ${style.border}`}
              style={{ left: position.x, top: position.y }}
            >
              <span className="flex items-center gap-1.5 text-xs font-semibold text-navy-900">
                <span className={`h-2.5 w-2.5 rounded-full ${style.dot}`} />
                <span className="truncate">{node.name}</span>
              </span>
              <span className="mt-0.5 block text-[11px] text-content-secondary">
                {node.overall_mastery == null ? style.label : `${style.label} · ${node.overall_mastery}%`}
              </span>
            </button>
          );
        })}
        </div>
      </div>
      {selected && (
        <div className="rounded-xl border border-surface-border p-4 text-sm text-navy-900" aria-live="polite">
          <h4 className="font-semibold">{selected.name}</h4>
          <p className="mt-1 text-xs text-content-secondary">{selected.description}</p>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
            <div><dt className="text-content-secondary">Overall mastery</dt><dd>{scoreText(selected.overall_mastery)}</dd></div>
            <div><dt className="text-content-secondary">LU</dt><dd>{scoreText(selected.lu)}</dd></div>
            <div><dt className="text-content-secondary">CU</dt><dd>{scoreText(selected.cu)}</dd></div>
            <div><dt className="text-content-secondary">CT</dt><dd>{scoreText(selected.ct)}</dd></div>
            <div><dt className="text-content-secondary">AU</dt><dd>{scoreText(selected.au)}</dd></div>
            <div><dt className="text-content-secondary">Attempts</dt><dd>{selected.attempt_count} ({selected.correct_count} correct, {selected.incorrect_count} incorrect)</dd></div>
          </dl>
          <h5 className="mt-3 text-xs font-semibold">Historical performance</h5>
          {selected.history.length === 0 ? (
            <p className="text-xs text-content-secondary">No assessed attempts yet.</p>
          ) : (
            <ul className="mt-1 space-y-1 text-xs">
              {selected.history.map((item) => (
                <li key={`${item.assessed_at}-${item.question_id}-${item.competency}`}>
                  {new Date(item.assessed_at).toLocaleDateString()} · {item.competency} {item.score}% · {item.awarded_marks}/{item.max_marks}
                </li>
              ))}
            </ul>
          )}
          <h5 className="mt-3 text-xs font-semibold">Prerequisite concepts</h5>
          {selected.prerequisites.length === 0 ? (
            <p className="text-xs text-content-secondary">None recorded.</p>
          ) : (
            <ul className="mt-1 space-y-1 text-xs">
              {selected.prerequisites.map((item) => (
                <li key={item.id}>{item.name} · {item.learning_status === 'not_assessed' ? 'Not assessed' : scoreText(item.overall_mastery)}</li>
              ))}
            </ul>
          )}
          <h5 className="mt-3 text-xs font-semibold">Recommended areas for improvement</h5>
          {selected.recommendations.length === 0 ? (
            <p className="text-xs text-content-secondary">No recommendation from the assessed evidence.</p>
          ) : (
            <ul className="mt-1 list-disc space-y-1 pl-4 text-xs">
              {selected.recommendations.map((item) => <li key={item}>{item}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export const KnowledgeComponentGraph: React.FC = () => {
  const [graph, setGraph] = useState<KnowledgeGraph | null>(null);
  const [recommendations, setRecommendations] = useState<Awaited<ReturnType<typeof apiClient.knowledgeGraph.myRecommendations>>>([]);
  const [subject, setSubject] = useState('all');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    apiClient.knowledgeGraph.mine().then((data) => {
      if (active) setGraph(data);
    }).catch((err) => {
      if (!active) return;
      setError(err instanceof ApiError ? err.message : 'Could not load your knowledge graph.');
    });
    apiClient.knowledgeGraph.myRecommendations().then((data) => {
      if (active) setRecommendations(data);
    }).catch(() => {
      if (active) setRecommendations([]);
    });
    return () => { active = false; };
  }, []);

  const subjects = graph ? [...new Set(graph.nodes.map((node) => node.subject))].sort() : [];
  const visible = graph && subject !== 'all'
    ? {
        ...graph,
        nodes: graph.nodes.filter((node) => node.subject === subject),
        edges: graph.edges.filter((edge) => {
          const ids = new Set(graph.nodes.filter((node) => node.subject === subject).map((node) => node.id));
          return ids.has(edge.source_id) && ids.has(edge.target_id);
        }),
      }
    : graph;

  return (
    <Card id="knowledge-graph" className="scroll-mt-6">
      <CardHeader
        title="Knowledge Component Graph"
        subtitle="Concepts your teacher added. Green is proficient, yellow is developing, red needs improvement, and grey is not assessed yet."
      />
      <CardBody className="space-y-4">
        {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
        {!error && !graph && <p role="status" className="text-sm">Loading your knowledge graph…</p>}
        {subjects.length > 0 && (
          <label className="block text-sm font-medium text-navy-900">
            Subject
            <select
              className="mt-1 block w-full max-w-xs rounded-lg border border-surface-border bg-white px-3 py-2 text-sm"
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
            >
              <option value="all">All subjects</option>
              {subjects.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
        )}
        {recommendations.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-navy-900">Questions matched to your results</h3>
            <ul className="space-y-2">
              {recommendations.map((item) => (
                <li key={`${item.kc_id}-${item.kind}`} className="rounded-lg border border-surface-border bg-white px-3 py-2 text-xs">
                  <p className="font-semibold text-navy-900">{item.kc_name} · {item.difficulty}</p>
                  <p className="mt-1 text-content-secondary">{item.reason}</p>
                  <p className="mt-1 text-content-secondary">
                    Previous result {item.previous_performance}. {item.expected_outcome}
                  </p>
                  {item.question ? (
                    <p className="mt-1 text-navy-900">{item.question.text}</p>
                  ) : (
                    <p className="mt-1 text-content-secondary">Your teacher does not have a saved question for this concept yet.</p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        {visible && <KnowledgeGraphView graph={visible} />}
      </CardBody>
    </Card>
  );
};
