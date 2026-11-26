import { describe, it, expect, vi } from 'vitest';
import { createNcertApi } from '../features/curriculum/api/ncertApi';
import { loadApiDataset } from '../lib/planningSyllabus';
import { syllabusFor } from '../lib/planning/syllabus';

vi.mock('../features/curriculum/api/ncertApi', async (original) => {
  const actual = await original<typeof import('../features/curriculum/api/ncertApi')>();
  return { ...actual, createNcertApi: vi.fn() };
});

const node = (id: string, kind: string, children: unknown[] = [], title: string | null = id) => ({
  id,
  identity_id: `i-${id}`,
  kind,
  title,
  children,
  verification: 'SOURCE_VERIFIED',
  citations: [{ document_type: 'TEXTBOOK', metadata_visible: true, title: 'Book', edition: 'First Edition', official_url: null, locator: `p-${id}`, source_id: 'TB', source_verification: 'FULL_REVIEW' }],
});

const tree: Record<string, unknown> = {
  s: node('s', 'SUBJECT', [node('c', 'CHAPTER')]),
  c: node('c', 'CHAPTER', [node('t', 'TOPIC')]),
  t: node('t', 'TOPIC', [node('st', 'SUBTOPIC'), node('o1', 'LEARNING_OUTCOME')]),
  st: node('st', 'SUBTOPIC'),
  o1: node('o1', 'LEARNING_OUTCOME'),
};

function mockApi(getNode: (id: string) => Promise<unknown>) {
  vi.mocked(createNcertApi).mockReturnValue({
    listReleases: async () => ({ items: [{ id: 'r', status: 'PUBLISHED', release_key: 'rel-1', edition: 'E1', academic_year: '2026-27' }], next_offset: null }),
    listSubjects: async () => ({ items: [{ id: 's', title: 'Mathematics' }], next_offset: null }),
    getNode,
  } as unknown as ReturnType<typeof createNcertApi>);
}

describe('published catalogue → planning syllabus', () => {
  it('loads every descendant from shallow node responses into chapters, units and outcome references', async () => {
    const getNode = vi.fn(async (id: string) => tree[id]);
    mockApi(getNode);
    const ds = await loadApiDataset(6, 'Mathematics', 'Admin');
    expect(ds.kind).toBe('PUBLISHED_API');
    expect(ds.nodes.map((n) => [n.id, n.kind, n.parentId])).toEqual([
      ['c', 'CHAPTER', null],
      ['t', 'TOPIC', 'c'],
      ['st', 'SUBTOPIC', 't'],
    ]);
    expect(ds.outcomes[0]).toMatchObject({ id: 'o1', linkedNodeIds: ['t'], inferred: false });
    expect(ds.nodes[1].provenance.locator).toBe('p-t');
    expect(getNode).toHaveBeenCalledWith('st');
    // A topic that is only the heading of a teachable subtopic is not a second unit (no parent + child double counting).
    const view = syllabusFor(ds, 6, 'Mathematics');
    expect(view.units.map((u) => u.id)).toEqual(['st']);
    expect(view.nodes.some((n) => n.id === 't')).toBe(true); // still part of the hierarchy
  });

  it('blocks hidden titles and never substitutes sample data when the API fails', async () => {
    mockApi(async (id: string) => (id === 't' ? node('t', 'TOPIC', [], null) : tree[id]));
    await expect(loadApiDataset(6, 'Mathematics', 'Admin')).rejects.toThrow(/hidden or missing titles/);
    vi.mocked(createNcertApi).mockReturnValue({
      listReleases: async () => {
        throw new Error('API offline');
      },
    } as unknown as ReturnType<typeof createNcertApi>);
    await expect(loadApiDataset(6, 'Science', 'Admin')).rejects.toThrow('API offline');
  });
});
