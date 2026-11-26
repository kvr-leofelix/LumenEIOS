import React, { useEffect, useState } from 'react';
import { apiClient } from '../../lib/apiClient';
import { nameInitial } from '../../lib/utils';
import { useData } from '../../context/DataContext';
import { useAuth } from '../../context/AuthContext';
import { Card, CardHeader, CardBody } from '../../components/common/Card';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Modal } from '../../components/common/Modal';
import { Users, Edit2, CheckCircle2 } from 'lucide-react';

export const TeacherAssignments: React.FC = () => {
  const { classes, workspace, teachers: workspaceTeachers, assignTeacherToClass, refreshWorkspace } = useData();
  const { availableUsers, currentSchoolId } = useAuth();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedClassId, setSelectedClassId] = useState('');
  const [selectedTeacherId, setSelectedTeacherId] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [toast, setToast] = useState<string | null>(null);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(timer);
  }, [toast]);

  // Live: the role-scoped workspace from the database. Offline demo: the seeded personas.
  const schoolClasses = classes.filter((c) => !currentSchoolId || c.schoolId === currentSchoolId);
  const allTeachers: { id: string; name: string; designation?: string; schoolId?: string }[] = workspace
    ? workspaceTeachers
    : availableUsers.filter((u) => u.role === 'teacher');
  const selectedClass = schoolClasses.find((c) => c.id === selectedClassId);
  // Only teachers of the class's own school can lead it (the server enforces the same rule).
  const teachers = allTeachers.filter((t) => !selectedClass || !t.schoolId || t.schoolId === selectedClass.schoolId);
  const staffCount = allTeachers.filter((t) => !currentSchoolId || !t.schoolId || t.schoolId === currentSchoolId).length;

  const handleOpenAssign = (classId: string, currentTeacherId: string | null | undefined) => {
    const cls = schoolClasses.find((c) => c.id === classId);
    const options = allTeachers.filter((t) => !cls || !t.schoolId || t.schoolId === cls.schoolId);
    setSelectedClassId(classId);
    setSelectedTeacherId(options.some((t) => t.id === currentTeacherId) ? currentTeacherId! : options[0]?.id ?? '');
    setSaveError('');
    setIsModalOpen(true);
  };

  const handleSaveAssignment = async (e: React.FormEvent) => {
    e.preventDefault();
    const teacher = teachers.find((t) => t.id === selectedTeacherId);
    if (!teacher || !selectedClassId || saving) return;
    setSaving(true);
    setSaveError('');
    try {
      if (workspace) {
        await apiClient.classes.assignTeacher(selectedClassId, teacher.id);
        await refreshWorkspace();
      } else {
        assignTeacherToClass(selectedClassId, teacher.id, teacher.name);
      }
      setIsModalOpen(false);
      setToast(`Assigned ${teacher.name} to ${selectedClass?.name ?? 'the class'}.`);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Could not save the assignment.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 bg-navy-900 text-white px-4 py-3 rounded-xl shadow-modal border border-teal-500/40 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-teal-400" />
          <span>{toast}</span>
        </div>
      )}

      {/* Header */}
      <div className="bg-white p-5 rounded-2xl border border-surface-border shadow-subtle flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-navy-900 tracking-tight">Faculty & Class Assignments</h1>
          <p className="text-xs text-content-secondary mt-0.5">
            Assign lead teachers to sections, manage subject allocations and instructional workloads
          </p>
        </div>

        <Badge variant="teal" size="sm">
          {staffCount} Active Teaching Staff
        </Badge>
      </div>

      {/* Classes Table */}
      <Card>
        <CardBody className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-surface-bg/80 text-content-secondary border-b border-surface-border">
                <tr>
                  <th className="py-3 px-4">Class Section</th>
                  <th className="py-3 px-4">Student Count</th>
                  <th className="py-3 px-4">Assigned Lead Teacher</th>
                  <th className="py-3 px-4">Core Subjects Covered</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border bg-white">
                {schoolClasses.map((cls) => (
                  <tr key={cls.id} className="hover:bg-surface-bg/40 transition-colors">
                    <td className="py-3 px-4 font-bold text-navy-900">{cls.name}</td>
                    <td className="py-3 px-4 text-content-secondary">{cls.studentCount} Students</td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-teal-50 text-teal-700 flex items-center justify-center font-bold text-xs border border-teal-200">
                          {nameInitial(cls.classTeacherName)}
                        </div>
                        <span className="font-semibold text-content-primary">{cls.classTeacherName || 'Not assigned'}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex flex-wrap gap-1">
                        {cls.subjectIds.map((sub) => (
                          <span
                            key={sub}
                            className="px-2 py-0.5 rounded text-[10px] bg-surface-bg border border-surface-border text-content-secondary uppercase"
                          >
                            {sub.replace('sub-', '')}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleOpenAssign(cls.id, cls.classTeacherId)}
                        icon={<Edit2 className="w-3.5 h-3.5" />}
                      >
                        Reassign
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>

      {/* Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Reassign Lead Faculty Member"
        subtitle="Select certified educator to manage class competency outcomes"
        maxWidth="md"
        footer={
          <div className="flex items-center justify-end gap-2.5 w-full">
            <Button variant="secondary" size="sm" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="teal" size="sm" onClick={handleSaveAssignment} disabled={saving || !selectedTeacherId} loading={saving}>
              Save Assignment
            </Button>
          </div>
        }
      >
        <form onSubmit={handleSaveAssignment} className="space-y-4 text-xs">
          {saveError && <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-rose-700">{saveError}</p>}
          <div>
            <label className="block font-semibold text-content-primary mb-1">Select Teacher</label>
            <select
              aria-label="Select Teacher"
              value={selectedTeacherId}
              onChange={(e) => setSelectedTeacherId(e.target.value)}
              className="w-full px-3 py-2 bg-white border border-surface-border rounded-lg text-xs"
            >
              {teachers.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.designation || 'Faculty'})
                </option>
              ))}
            </select>
          </div>
        </form>
      </Modal>
    </div>
  );
};

