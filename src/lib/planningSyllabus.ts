/**
 * Loads a published NCERT catalogue release from the existing backend API (/api/v1/ncert) into the planning
 * syllabus model as a PUBLISHED_API dataset. Never falls back to sample data: any failure is surfaced to the caller.
 */
import { createNcertApi, fetchAllPages } from '../features/curriculum/api/ncertApi';
import type { CatalogueNode } from '../features/curriculum/api/contract';
import type { PlanningSubject } from './planning/calendar';
import type { OutcomeReference, SyllabusDataset, SyllabusNode, Textbook } from './planning/syllabus';

const KIND_MAP: Record<string, SyllabusNode['kind'] | undefined> = { CHAPTER: 'CHAPTER', TOPIC: 'TOPIC', SUBTOPIC: 'SUBTOPIC' };

export async function loadApiDataset(grade: number, subject: PlanningSubject, importedBy: string): Promise<SyllabusDataset> {
  const api = createNcertApi();
  const releases = await fetchAllPages((offset) => api.listReleases({ offset, limit: 100 }));
  const release = releases.find((r) => r.status === 'PUBLISHED');
  if (!release) throw new Error('No published NCERT catalogue release is available from the backend.');
  const subjects = await fetchAllPages((offset) => api.listSubjects({ releaseId: release.id, grade, offset, limit: 100 }));
  const selected = subjects.find((s) => s.title?.toLowerCase() === subject.toLowerCase());
  if (!selected) throw new Error(`The published release has no Class ${grade} ${subject} subject.`);
  const datasetId = `api-${release.release_key}-${grade}-${subject}`;
  const root = await api.getNode(selected.id);
  const cite = root.citations.find((c) => c.document_type === 'TEXTBOOK' && c.metadata_visible) ?? root.citations.find((c) => c.metadata_visible);
  const textbook: Textbook = {
    id: `${datasetId}-book`,
    datasetId,
    grade,
    subject,
    language: 'en',
    code: cite?.source_id ?? '',
    title: cite?.title ?? `Published catalogue release ${release.release_key}`,
    part: '',
    edition: cite?.edition ?? release.edition,
    reprint: 'Not stated',
    publicationYear: release.academic_year ?? '',
    editionVerification: cite?.source_verification ?? 'UNSTATED',
    evidenceUrl: cite?.official_url ?? '',
    locator: cite?.locator ?? '',
  };
  const nodes: SyllabusNode[] = [];
  const outcomes: OutcomeReference[] = [];
  let seq = 0;
  // Node responses contain only immediate children, so every descendant is fetched before it is classified.
  const walk = async (n: CatalogueNode, parentId: string | null, chapterNo: string): Promise<void> => {
    const kind = KIND_MAP[n.kind];
    let nextParent = parentId;
    let nextChapter = chapterNo;
    if (n.kind === 'LEARNING_OUTCOME') {
      if (!n.title) throw new Error('The published syllabus contains hidden or missing outcome titles; loading is blocked.');
      outcomes.push({
        id: n.id,
        datasetId,
        grade,
        subject,
        sourceTitle: n.citations[0]?.title ?? 'Published catalogue',
        edition: n.citations[0]?.edition ?? release.edition,
        officialUrl: n.citations[0]?.official_url ?? '',
        locator: n.citations[0]?.locator ?? '',
        researchLabel: n.title,
        identifierStatus: n.verification,
        linkedNodeIds: parentId ? [parentId] : [],
        relationshipBasis: 'Catalogue hierarchy',
        linkVerification: n.verification,
        applicability: 'UNVERIFIED',
        inferred: n.verification !== 'EXPERT_VERIFIED' && n.verification !== 'SOURCE_VERIFIED',
      });
    } else if (kind) {
      if (!n.title) throw new Error('The published syllabus contains hidden or missing titles; loading is blocked.');
      seq += 1;
      if (kind === 'CHAPTER') nextChapter = String(nodes.filter((x) => x.kind === 'CHAPTER').length + 1);
      nodes.push({
        id: n.id,
        datasetId,
        textbookId: textbook.id,
        grade,
        subject,
        kind,
        parentId: kind === 'CHAPTER' ? null : parentId,
        number: kind === 'CHAPTER' ? nextChapter : '',
        title: n.title,
        sequence: seq,
        provenance: {
          datasetId,
          sourceId: n.identity_id,
          officialUrl: n.citations[0]?.official_url ?? undefined,
          locator: n.citations.map((c) => c.locator).filter(Boolean).join('; ') || 'No locator in API response',
          verification: n.verification,
        },
      });
      nextParent = n.id;
    }
    for (const child of n.children) await walk(await api.getNode(child.id), nextParent, nextChapter);
  };
  await walk(root, null, '');
  if (!nodes.some((n) => n.kind !== 'CHAPTER')) throw new Error('The published release contains no topics for this class and subject.');
  return {
    id: datasetId,
    kind: 'PUBLISHED_API',
    label: `Published NCERT catalogue ${release.release_key} — Class ${grade} ${subject}`,
    description: 'Loaded from the backend catalogue API. Completeness and school applicability require review.',
    importedAt: new Date().toISOString(),
    importedBy,
    textbooks: [textbook],
    nodes,
    outcomes,
  };
}
