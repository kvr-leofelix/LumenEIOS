import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../../components/common/Button';
import { Card, CardBody, CardHeader } from '../../components/common/Card';
import { useAuth } from '../../context/AuthContext';
import { ApiError, apiClient, type DemoWalkthrough } from '../../lib/apiClient';
import { UnauthorizedPage } from '../shared/UnauthorizedPage';
import { KnowledgeGraphView, type KnowledgeGraph } from '../student/KnowledgeComponentGraph';
import { samplesFor, type SampleConcept } from './kcSamples';

const inputClass = 'mt-1 block w-full rounded-lg border border-surface-border bg-white px-3 py-2 text-sm';

type ComponentRow = Awaited<ReturnType<typeof apiClient.knowledgeGraph.list>>[number];
type RelationshipRow = Awaited<ReturnType<typeof apiClient.knowledgeGraph.relationships>>[number];
type RelationshipKind = RelationshipRow['relationship'];

const RELATIONSHIP_LABEL: Record<RelationshipKind, string> = {
  PREREQUISITE_OF: 'is a prerequisite of',
  PART_OF: 'is part of',
  RELATED_TO: 'is related to',
};

function message(err: unknown) {
  return err instanceof ApiError ? err.message : 'Could not save.';
}

/** First (source, target) pair with no link either way and no path back from target to source. */
function linkablePair(concepts: Array<{ id: string }>, links: Array<{ source_id: string; target_id: string }>): [string, string] {
  const next = new Map<string, string[]>();
  links.forEach((l) => next.set(l.source_id, [...(next.get(l.source_id) ?? []), l.target_id]));
  const reaches = (from: string, to: string) => {
    const seen = new Set<string>(); const stack = [from];
    while (stack.length) { const id = stack.pop()!; if (id === to) return true; if (seen.has(id)) continue; seen.add(id); stack.push(...(next.get(id) ?? [])); }
    return false;
  };
  const linked = (a: string, b: string) => links.some((l) => (l.source_id === a && l.target_id === b) || (l.source_id === b && l.target_id === a));
  for (const a of concepts) for (const b of concepts) {
    if (a.id !== b.id && !linked(a.id, b.id) && !reaches(b.id, a.id)) return [a.id, b.id];
  }
  return [concepts[0]?.id || '', concepts[1]?.id || concepts[0]?.id || ''];
}

function sameText(left: string, right: string) {
  return left.trim().toLowerCase() === right.trim().toLowerCase();
}

function uniqueSamples(items: SampleConcept[], field: keyof SampleConcept) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const value = item[field];
    if (seen.has(value)) return false;
    seen.add(value);
    return true;
  });
}

export function KnowledgeComponentsPage() {
  const { currentUser } = useAuth();
  if (!currentUser || !['teacher', 'admin', 'principal'].includes(currentUser.role)) {
    return <UnauthorizedPage />;
  }
  return <Catalogue key={`${currentUser.id}:${currentUser.schoolId}`} />;
}

function Catalogue() {
  const { currentUser } = useAuth();
  const [subjects, setSubjects] = useState<Array<{ id: string; name: string }>>([]);
  const [subjectId, setSubjectId] = useState('');
  const [components, setComponents] = useState<ComponentRow[]>([]);
  const [relationships, setRelationships] = useState<RelationshipRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState('');
  const [topic, setTopic] = useState('');
  const [description, setDescription] = useState('');
  const seededSubjects = useRef(new Set<string>());
  const [sourceId, setSourceId] = useState('');
  const [targetId, setTargetId] = useState('');
  const [kind, setKind] = useState<RelationshipKind>('PREREQUISITE_OF');
  const [revision, setRevision] = useState(0);
  const [preview, setPreview] = useState<DemoWalkthrough | null>(null);

  useEffect(() => {
    let active = true;
    apiClient.assessments.targets()
      .then((classes) => {
        if (!active) return;
        const byId = new Map<string, string>();
        classes.forEach((section) => section.subjects.forEach((subject) => byId.set(subject.id, subject.name)));
        const rows = [...byId.entries()].map(([id, subjectName]) => ({ id, name: subjectName }))
          .sort((a, b) => a.name.localeCompare(b.name));
        setSubjects(rows);
        setSubjectId((current) => current || rows[0]?.id || '');
        setLoading(false);
      })
      .catch((err) => {
        if (!active) return;
        setError(message(err));
        setLoading(false);
      });
    return () => { active = false; };
  }, []);

  const subjectName = subjects.find((subject) => subject.id === subjectId)?.name ?? '';
  const samples = samplesFor(subjectName);

  // Start each subject with an empty form; the name field suggests the sample concepts not added yet.
  useEffect(() => {
    setName('');
    setTopic('');
    setDescription('');
  }, [subjectId, subjectName]);

  useEffect(() => {
    if (!subjectId) return;
    let active = true;
    setError('');
    const pack = samplesFor(subjectName);
    (async () => {
      try {
        let concepts = await apiClient.knowledgeGraph.list(subjectId);
        if (!seededSubjects.current.has(subjectId)) {
          seededSubjects.current.add(subjectId);
          const missing = pack.concepts.filter((sample) => !concepts.some(
            (item) => sameText(item.name, sample.name) && sameText(item.topic, sample.topic),
          ));
          for (const sample of missing) {
            try {
              await apiClient.knowledgeGraph.create({
                name: sample.name,
                description: sample.description,
                subject_id: subjectId,
                topic: sample.topic,
              });
            } catch (err) {
              if (!(err instanceof ApiError && err.status === 409)) throw err;
            }
          }
          concepts = await apiClient.knowledgeGraph.list(subjectId);
          const byName = new Map(concepts.map((item) => [item.name, item]));
          for (const sampleLink of pack.links) {
            const source = byName.get(sampleLink.source);
            const target = byName.get(sampleLink.target);
            if (!source || !target || source.id === target.id) continue;
            try {
              await apiClient.knowledgeGraph.link({
                source_id: source.id,
                target_id: target.id,
                relationship: sampleLink.relationship,
              });
            } catch (err) {
              if (!(err instanceof ApiError && (err.status === 422 || err.status === 409))) throw err;
            }
          }
        }
        const links = await apiClient.knowledgeGraph.relationships(subjectId);
        if (!active) return;
        setComponents(concepts);
        setRelationships(links);
        // Open the link form on a pair that is not linked yet and would not form a cycle, so it can be saved as is.
        const [firstSource, firstTarget] = linkablePair(concepts, links);
        setSourceId((current) => concepts.some((item) => item.id === current) ? current : firstSource);
        setTargetId((current) => concepts.some((item) => item.id === current) ? current : firstTarget);
      } catch (err) {
        if (active) setError(message(err));
      }
    })();
    return () => { active = false; };
  }, [subjectId, subjectName, revision]);

  useEffect(() => {
    if (!subjectId) return;
    let active = true;
    apiClient.knowledgeGraph.demoPreview(subjectId).then((data) => {
      if (active) setPreview(data);
    }).catch(() => {
      if (active) setPreview(null);
    });
    return () => { active = false; };
  }, [subjectId, revision]);

  const names = new Map(components.map((item) => [item.id, item.name]));
  const choices: SampleConcept[] = [...samples.concepts];
  components.forEach((item) => {
    if (!choices.some((sample) => sameText(sample.name, item.name) && sameText(sample.topic, item.topic))) {
      choices.push({ name: item.name, topic: item.topic, description: item.description });
    }
  });
  const topics = uniqueSamples(choices, 'topic');
  // Sample concepts the subject does not have yet (the name field suggests these).
  const unsaved = samples.concepts.filter((sample) => !components.some(
    (item) => sameText(item.name, sample.name) && sameText(item.topic, sample.topic)));

  function chooseConcept(nextName: string) {
    const match = choices.find((item) => item.name === nextName);
    setName(nextName);
    if (match) {
      setTopic(match.topic);
      setDescription(match.description);
    }
  }

  async function addConcept(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError('');
    setNotice('');
    try {
      await apiClient.knowledgeGraph.create({
        name: name.trim(),
        description: description.trim(),
        subject_id: subjectId,
        topic: topic.trim(),
      });
      setRevision((value) => value + 1);
      setName(''); setTopic(''); setDescription('');
      setNotice('Concept saved. It now appears on this page and on the student graph.');
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setNotice('That concept is already saved. Students can see it on their graph.');
      } else {
        setError(message(err));
      }
    } finally {
      setSaving(false);
    }
  }

  async function addLink(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError('');
    setNotice('');
    try {
      await apiClient.knowledgeGraph.link({ source_id: sourceId, target_id: targetId, relationship: kind });
      setRevision((value) => value + 1);
      setNotice('Link saved. Students see the same link on their graph.');
    } catch (err) {
      setError(message(err));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p role="status" className="text-sm">Loading subjects…</p>;

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <Card>
        <CardHeader
          title="Knowledge Components"
          subtitle="Add the concepts for a subject. Evaluation can attach a question only to a concept that already exists here."
        />
        <CardBody className="space-y-4">
          {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
          {notice && <p role="status" className="text-sm text-teal-800">{notice}</p>}
          {subjects.length === 0 ? (
            <p className="text-sm text-content-secondary">This school has no class subjects yet.</p>
          ) : (
            <label className="block text-sm font-medium text-navy-900">
              Subject
              <select id="kc-subject" className={inputClass} value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
                {subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
              </select>
            </label>
          )}
          <p className="text-xs text-content-secondary">
            Step 1. This graph is what the student persona sees for the subject. Grey concepts are not marked yet. {currentUser?.role === 'teacher' || currentUser?.role === 'developer'
              ? <>Open <Link className="font-semibold text-teal-700 underline" to="/upload">Upload</Link> and evaluate the sample answer to colour them in.</>
              : 'A teacher colours them in by evaluating the sample answer on Upload.'}
          </p>
        </CardBody>
      </Card>

      {preview && (
        <Card>
          <CardHeader
            title={`${preview.subject_name} concept graph`}
            subtitle={`${preview.student_name} sees this graph. ${preview.evaluated ? 'The sample paper has been marked.' : 'Mark the sample paper on Upload to add scores.'}`}
          />
          <CardBody>
            <KnowledgeGraphView graph={preview.graph as KnowledgeGraph} />
          </CardBody>
        </Card>
      )}

      {subjectId && (
        <Card>
          <CardHeader title="Add a concept" subtitle="The same name and topic cannot be added twice for one subject." />
          <CardBody>
            <form onSubmit={addConcept} className="grid gap-4 sm:grid-cols-2">
              <label className="text-sm font-medium text-navy-900">
                Name
                <input className={inputClass} value={name} list="kc-name-suggestions" required maxLength={255}
                  placeholder="e.g. Fractions" onChange={(event) => chooseConcept(event.target.value)} />
                <datalist id="kc-name-suggestions">
                  {unsaved.map((item) => <option key={`${item.name}-${item.topic}`} value={item.name} />)}
                </datalist>
              </label>
              <label className="text-sm font-medium text-navy-900">
                Topic
                <input className={inputClass} value={topic} list="kc-topic-suggestions" required maxLength={255}
                  placeholder="e.g. Number system" onChange={(event) => setTopic(event.target.value)} />
                <datalist id="kc-topic-suggestions">
                  {topics.map((item) => <option key={item.topic} value={item.topic} />)}
                </datalist>
              </label>
              <label className="text-sm font-medium text-navy-900 sm:col-span-2">
                Description
                <textarea className={inputClass} rows={2} value={description} maxLength={1000}
                  placeholder="What a student should understand about this concept"
                  onChange={(event) => setDescription(event.target.value)} />
              </label>
              {unsaved.length > 0 && <p className="text-xs text-content-secondary sm:col-span-2">
                Suggestions not yet added: {unsaved.map((item) => item.name).join(', ')}.</p>}
              <div>
                <Button type="submit" variant="teal" loading={saving} disabled={saving}>Add concept</Button>
              </div>
            </form>
          </CardBody>
        </Card>
      )}

      {components.length > 0 && (
        <Card>
          <CardHeader title="Concepts for this subject" />
          <CardBody>
            <ul className="space-y-2 text-sm">
              {components.map((item) => (
                <li key={item.id}>
                  <span className="font-medium text-navy-900">{item.name}</span>
                  <span className="text-content-secondary"> · {item.topic}</span>
                  {item.description && <p className="text-xs text-content-secondary">{item.description}</p>}
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      )}

      {components.length >= 2 && (
        <Card>
          <CardHeader
            title="Link two concepts"
            subtitle="Prerequisite means the first concept comes before the second. A link cannot point at itself or form a cycle."
          />
          <CardBody>
            <form onSubmit={addLink} className="grid gap-4 sm:grid-cols-3">
              <label className="text-sm font-medium text-navy-900">
                From
                <select className={inputClass} value={sourceId} onChange={(event) => setSourceId(event.target.value)}>
                  {components.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
              <label className="text-sm font-medium text-navy-900">
                Relationship
                <select className={inputClass} value={kind} onChange={(event) => setKind(event.target.value as RelationshipKind)}>
                  <option value="PREREQUISITE_OF">is a prerequisite of</option>
                  <option value="PART_OF">is part of</option>
                  <option value="RELATED_TO">is related to</option>
                </select>
              </label>
              <label className="text-sm font-medium text-navy-900">
                To
                <select className={inputClass} value={targetId} onChange={(event) => setTargetId(event.target.value)}>
                  {components.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
              <div className="sm:col-span-3">
                <Button type="submit" variant="outline" loading={saving} disabled={saving}>Link concepts</Button>
              </div>
            </form>
            {relationships.length > 0 && (
              <ul className="mt-4 space-y-1 text-sm text-navy-900">
                {relationships.map((link) => (
                  <li key={link.id}>
                    {names.get(link.source_id) ?? link.source_id} {RELATIONSHIP_LABEL[link.relationship]} {names.get(link.target_id) ?? link.target_id}
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      )}
    </div>
  );
}
