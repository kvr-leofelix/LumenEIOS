# LearnSphere comparison inventory

Comparison against KVR baseline `0831c65`; line endings normalized. Runtime/generated directories, credentials and databases excluded. Status describes the starting point, not final verification.

| Source-relative file | Baseline comparison |
|---|---|
| `backend/alembic.ini` | identical at baseline |
| `backend/app/api/dependencies.py` | target differs |
| `backend/app/api/v1/admin.py` | target differs |
| `backend/app/api/v1/assessment_results.py` | identical at baseline |
| `backend/app/api/v1/assessments.py` | target differs |
| `backend/app/api/v1/audit.py` | target differs |
| `backend/app/api/v1/auth.py` | target differs |
| `backend/app/api/v1/calendar.py` | target differs |
| `backend/app/api/v1/classes.py` | target differs |
| `backend/app/api/v1/competencies.py` | target differs |
| `backend/app/api/v1/curriculum.py` | target differs |
| `backend/app/api/v1/documents.py` | target differs |
| `backend/app/api/v1/model_registry.py` | target differs |
| `backend/app/api/v1/notifications.py` | target differs |
| `backend/app/api/v1/ocr.py` | target differs |
| `backend/app/api/v1/onboarding.py` | identical at baseline |
| `backend/app/api/v1/reports.py` | target differs |
| `backend/app/api/v1/router.py` | target differs |
| `backend/app/api/v1/schools.py` | target differs |
| `backend/app/api/v1/teachers.py` | identical at baseline |
| `backend/app/api/v1/time_aware.py` | target differs |
| `backend/app/api/v1/users.py` | target differs |
| `backend/app/core/config.py` | target differs |
| `backend/app/core/logging.py` | identical at baseline |
| `backend/app/core/permissions.py` | target differs |
| `backend/app/core/security.py` | target differs |
| `backend/app/db/base.py` | target differs |
| `backend/app/db/session.py` | target differs |
| `backend/app/lib/__init__.py` | identical at baseline |
| `backend/app/lib/class_names.py` | target differs |
| `backend/app/lib/question_content.py` | source-only |
| `backend/app/lib/question_distribution.py` | source-only |
| `backend/app/main.py` | target differs |
| `backend/app/models/entities.py` | target differs |
| `backend/app/modules/differentiated_homework/__init__.py` | identical at baseline |
| `backend/app/modules/differentiated_homework/access.py` | identical at baseline |
| `backend/app/modules/differentiated_homework/competency_adapter.py` | identical at baseline |
| `backend/app/modules/differentiated_homework/draft_service.py` | identical at baseline |
| `backend/app/modules/differentiated_homework/gap_analyzer.py` | identical at baseline |
| `backend/app/modules/differentiated_homework/homework_assembler.py` | identical at baseline |
| `backend/app/modules/differentiated_homework/models.py` | target differs |
| `backend/app/modules/differentiated_homework/question_bank_adapter.py` | target differs |
| `backend/app/modules/differentiated_homework/question_selector.py` | identical at baseline |
| `backend/app/modules/differentiated_homework/README.md` | target differs |
| `backend/app/modules/differentiated_homework/router.py` | target differs |
| `backend/app/modules/differentiated_homework/schemas.py` | target differs |
| `backend/app/modules/differentiated_homework/student_access.py` | target differs |
| `backend/app/modules/differentiated_homework/submission_service.py` | identical at baseline |
| `backend/app/modules/learnsphere/__init__.py` | identical at baseline |
| `backend/app/modules/learnsphere/access.py` | identical at baseline |
| `backend/app/modules/learnsphere/assessment_models.py` | identical at baseline |
| `backend/app/modules/learnsphere/automation.py` | source-only |
| `backend/app/modules/learnsphere/evidence_service.py` | identical at baseline |
| `backend/app/modules/learnsphere/models.py` | identical at baseline |
| `backend/app/modules/learnsphere/router.py` | target differs |
| `backend/app/modules/learnsphere/schemas.py` | identical at baseline |
| `backend/app/schemas/assessment_learning.py` | target differs |
| `backend/app/schemas/assessment_results.py` | identical at baseline |
| `backend/app/schemas/assessments.py` | target differs |
| `backend/app/schemas/auth.py` | target differs |
| `backend/app/schemas/calendar.py` | identical at baseline |
| `backend/app/schemas/common.py` | identical at baseline |
| `backend/app/schemas/competencies.py` | target differs |
| `backend/app/schemas/curriculum.py` | identical at baseline |
| `backend/app/schemas/model_registry.py` | identical at baseline |
| `backend/app/schemas/ocr.py` | target differs |
| `backend/app/schemas/panchapadi.py` | identical at baseline |
| `backend/app/schemas/schools.py` | target differs |
| `backend/app/schemas/teachers.py` | identical at baseline |
| `backend/app/schemas/time_aware.py` | target differs |
| `backend/app/seed/__init__.py` | identical at baseline |
| `backend/app/seed/seed_data.py` | target differs |
| `backend/app/services/assessment_audience.py` | target differs |
| `backend/app/services/assessment_guidance.py` | target differs |
| `backend/app/services/assessment_learning.py` | target differs |
| `backend/app/services/assessment_results.py` | identical at baseline |
| `backend/app/services/batch_grading_service.py` | target differs |
| `backend/app/services/competency_service.py` | identical at baseline |
| `backend/app/services/knowledge_graph_service.py` | identical at baseline |
| `backend/app/services/llm_service.py` | target differs |
| `backend/app/services/model_training_service.py` | identical at baseline |
| `backend/app/services/ocr_service.py` | target differs |
| `backend/app/services/panchapadi.py` | target differs |
| `backend/app/services/progress.py` | identical at baseline |
| `backend/app/services/storage_service.py` | target differs |
| `backend/app/services/time_aware_engine.py` | target differs |
| `backend/app/services/web_source.py` | identical at baseline |
| `backend/migrations/env.py` | identical at baseline |
| `backend/migrations/v1_schema.py` | identical at baseline |
| `backend/migrations/versions/0001_add_learnsphere.py` | identical at baseline |
| `backend/migrations/versions/0002_assessment_results.py` | identical at baseline |
| `backend/migrations/versions/0003_panchapadi.py` | identical at baseline |
| `backend/migrations/versions/0004_unmapped_activities.py` | identical at baseline |
| `backend/requirements-ocr.txt` | target differs |
| `backend/requirements.txt` | target differs |
| `backend/scripts/__init__.py` | identical at baseline |
| `backend/scripts/migrate_learnsphere.py` | identical at baseline |
| `backend/scripts/reprocess_assessment_learning.py` | identical at baseline |
| `backend/scripts/reset_roster.py` | identical at baseline |
| `backend/tests/__init__.py` | identical at baseline |
| `backend/tests/conftest.py` | target differs |
| `backend/tests/sample_seed.py` | identical at baseline |
| `backend/tests/test_ai_generation_and_batch_grading.py` | target differs |
| `backend/tests/test_api.py` | target differs |
| `backend/tests/test_assessment_learning_automation.py` | identical at baseline |
| `backend/tests/test_assessment_learnsphere_connection.py` | target differs |
| `backend/tests/test_assignment_uploads.py` | target differs |
| `backend/tests/test_competency_calculations.py` | identical at baseline |
| `backend/tests/test_demo_root.py` | target differs |
| `backend/tests/test_guidance_recovery.py` | target differs |
| `backend/tests/test_guidance_visibility.py` | identical at baseline |
| `backend/tests/test_homework_assembly.py` | identical at baseline |
| `backend/tests/test_homework_assignments.py` | target differs |
| `backend/tests/test_homework_drafts.py` | target differs |
| `backend/tests/test_homework_gap_analysis_api.py` | identical at baseline |
| `backend/tests/test_homework_gap_analyzer.py` | identical at baseline |
| `backend/tests/test_homework_preview_api.py` | identical at baseline |
| `backend/tests/test_homework_question_selection.py` | identical at baseline |
| `backend/tests/test_homework_submission_api.py` | target differs |
| `backend/tests/test_homework_submissions.py` | identical at baseline |
| `backend/tests/test_learnsphere.py` | target differs |
| `backend/tests/test_learnsphere_automation_scope.py` | source-only |
| `backend/tests/test_learnsphere_improvements.py` | identical at baseline |
| `backend/tests/test_ocr_and_review.py` | identical at baseline |
| `backend/tests/test_onboarding.py` | identical at baseline |
| `backend/tests/test_panchapadi.py` | identical at baseline |
| `backend/tests/test_permissions.py` | identical at baseline |
| `backend/tests/test_qwen_gpu_smoke.py` | identical at baseline |
| `backend/tests/test_qwen_ocr_preview.py` | target differs |
| `backend/tests/test_qwen_question_generation.py` | target differs |
| `backend/tests/test_roster_seed.py` | target differs |
| `backend/tests/test_school_boundaries.py` | target differs |
| `backend/tests/test_student_homework_access.py` | target differs |
| `backend/tests/test_studio_assignment_school_audience.py` | source-only |
| `backend/tests/test_studio_competencies_and_manual.py` | source-only |
| `backend/tests/test_studio_counts_and_deletion.py` | source-only |
| `backend/tests/test_studio_review_timeout.py` | source-only |
| `backend/tests/test_studio_web_sources.py` | target differs |
| `backend/tests/test_time_aware_engine.py` | target differs |
| `src/App.tsx` | target differs |
| `src/components/charts/ClassHeatmap.tsx` | identical at baseline |
| `src/components/charts/CompetencyBarChart.tsx` | target differs |
| `src/components/charts/CompetencyRadarChart.tsx` | target differs |
| `src/components/charts/PacingProgressChart.tsx` | identical at baseline |
| `src/components/common/AssessmentResultsReview.tsx` | target differs |
| `src/components/common/Badge.tsx` | identical at baseline |
| `src/components/common/Button.tsx` | identical at baseline |
| `src/components/common/Card.tsx` | identical at baseline |
| `src/components/common/CompetencyScoreBadge.tsx` | identical at baseline |
| `src/components/common/HoverTip.tsx` | identical at baseline |
| `src/components/common/KPICard.tsx` | identical at baseline |
| `src/components/common/ManualQuestionForm.tsx` | source-only |
| `src/components/common/Modal.tsx` | target differs |
| `src/components/common/ProcessProgress.tsx` | identical at baseline |
| `src/components/common/SearchInput.tsx` | identical at baseline |
| `src/components/common/StudentAssessments.tsx` | target differs |
| `src/components/layout/AppLayout.tsx` | target differs |
| `src/components/layout/FontSizeControl.tsx` | identical at baseline |
| `src/components/layout/RoleSwitcherBanner.tsx` | target differs |
| `src/components/layout/Sidebar.tsx` | target differs |
| `src/components/layout/ThemeMenu.tsx` | target differs |
| `src/components/layout/Topbar.tsx` | target differs |
| `src/components/learnsphere/AssessmentLearningEditor.tsx` | identical at baseline |
| `src/components/learnsphere/AssessmentPerformanceSummary.tsx` | identical at baseline |
| `src/components/learnsphere/AssessmentQuestionSupport.tsx` | target differs |
| `src/components/learnsphere/CompetencyReview.tsx` | source-only |
| `src/components/learnsphere/GuidanceAudienceItems.tsx` | identical at baseline |
| `src/components/learnsphere/LearningTimeline.tsx` | identical at baseline |
| `src/components/learnsphere/LearnSphereResultReview.tsx` | source-only |
| `src/components/learnsphere/PanchapadiEvaluation.tsx` | identical at baseline |
| `src/components/learnsphere/PanchapadiMappingEditor.tsx` | target differs |
| `src/components/learnsphere/PanchapadiProgress.tsx` | target differs |
| `src/components/learnsphere/StudentScopeSelector.tsx` | identical at baseline |
| `src/components/school/SchoolPerformance.tsx` | target differs |
| `src/context/AuthContext.tsx` | target differs |
| `src/context/DataContext.tsx` | target differs |
| `src/context/ThemeContext.tsx` | target differs |
| `src/data/seedData.ts` | target differs |
| `src/index.css` | identical at baseline |
| `src/lib/apiClient.ts` | target differs |
| `src/lib/assessmentResults.ts` | target differs |
| `src/lib/calculations.ts` | target differs |
| `src/lib/className.ts` | identical at baseline |
| `src/lib/demoOcr.ts` | identical at baseline |
| `src/lib/learnsphere.ts` | target differs |
| `src/lib/permissions.ts` | target differs |
| `src/lib/questionStudio.ts` | source-only |
| `src/lib/utils.ts` | target differs |
| `src/main.tsx` | target differs |
| `src/pages/admin/AcademicConfig.tsx` | target differs |
| `src/pages/admin/AdminDashboard.tsx` | target differs |
| `src/pages/admin/AuditLogs.tsx` | target differs |
| `src/pages/admin/SchoolsManagement.tsx` | target differs |
| `src/pages/admin/UsersManagement.tsx` | target differs |
| `src/pages/auth/LoginPage.tsx` | target differs |
| `src/pages/learnsphere/ActivityWorkspace.tsx` | target differs |
| `src/pages/learnsphere/LearningJourney.tsx` | identical at baseline |
| `src/pages/learnsphere/LearningSupport.tsx` | target differs |
| `src/pages/learnsphere/LearnSphereLayout.tsx` | identical at baseline |
| `src/pages/learnsphere/RealLifeMissions.tsx` | identical at baseline |
| `src/pages/learnsphere/TeachBackChallenge.tsx` | identical at baseline |
| `src/pages/parent/ParentDashboard.tsx` | target differs |
| `src/pages/principal/CurriculumOversight.tsx` | target differs |
| `src/pages/principal/PrincipalDashboard.tsx` | target differs |
| `src/pages/principal/PrincipalReports.tsx` | target differs |
| `src/pages/principal/SchoolPerformancePage.tsx` | target differs |
| `src/pages/principal/SchoolStudents.tsx` | identical at baseline |
| `src/pages/principal/SchoolTeachers.tsx` | target differs |
| `src/pages/principal/TeacherAssignments.tsx` | target differs |
| `src/pages/shared/NotFoundPage.tsx` | identical at baseline |
| `src/pages/shared/OnboardingPage.tsx` | identical at baseline |
| `src/pages/shared/UnauthorizedPage.tsx` | target differs |
| `src/pages/shared/WelcomePage.tsx` | identical at baseline |
| `src/pages/student/StudentAnswerSheets.tsx` | source-only |
| `src/pages/student/StudentDashboard.tsx` | target differs |
| `src/pages/student/StudentRecords.tsx` | target differs |
| `src/pages/teacher/AssessmentBuilder.tsx` | target differs |
| `src/pages/teacher/CurriculumPlanner180.tsx` | target differs |
| `src/pages/teacher/MyClasses.tsx` | target differs |
| `src/pages/teacher/RemediationManager.tsx` | identical at baseline |
| `src/pages/teacher/ScanReview.tsx` | target differs |
| `src/pages/teacher/StudentHomework.tsx` | source-only |
| `src/pages/teacher/TeacherDashboard.tsx` | target differs |
| `src/pages/time-aware/CompressionPreviewModal.tsx` | source-only |
| `src/pages/time-aware/TimeAwareEngine.tsx` | target differs |
| `src/styles/themes.css` | target differs |
| `src/types/assessmentGuidance.ts` | target differs |
| `src/types/assessmentResults.ts` | identical at baseline |
| `src/types/index.ts` | target differs |
| `src/types/learnsphere.ts` | identical at baseline |
| `src/types/panchapadi.ts` | identical at baseline |
| `tests/assessment-results-ui.mjs` | target differs |
| `tests/guidance-visibility-ui.mjs` | identical at baseline |
| `tests/learnsphere-automation-ui.mjs` | source-only |
| `tests/learnsphere-ui.mjs` | identical at baseline |
| `tests/studio-live-preview.mjs` | source-only |
| `tests/studio-ui.mjs` | source-only |
| `docs/architecture.md` | target differs |
| `docs/assessment-learning-automation.md` | identical at baseline |
| `docs/assessment-learnsphere-connection.md` | identical at baseline |
| `docs/database-schema.md` | target differs |
| `docs/deployment.md` | identical at baseline |
| `docs/frontend-api-mapping.md` | target differs |
| `docs/learnsphere-automation-report.md` | source-only |
| `docs/learnsphere-guidance-evidence-corrections.md` | identical at baseline |
| `docs/learnsphere-implementation-report.md` | source-only |
| `docs/learnsphere-improvements.md` | identical at baseline |
| `docs/learnsphere-migrations.md` | identical at baseline |
| `docs/learnsphere.md` | identical at baseline |
| `docs/model-training.md` | identical at baseline |
| `docs/ocr-gpu-deployment.md` | identical at baseline |
| `docs/ocr-implementation.md` | target differs |
| `docs/ocr-pipeline.md` | identical at baseline |
| `docs/panchapadi-assessments.md` | identical at baseline |
| `docs/question-studio.md` | source-only |
| `docs/security.md` | target differs |
| `docs/time-aware-engine.md` | identical at baseline |
| `docs/vast-ai-deployment.md` | target differs |
| `infrastructure/docker-compose.yml` | target differs |

## Application-root configuration comparison

Retained target package.json, package-lock.json, vite.config.ts, .env.example, backend requirement files and infrastructure/docker-compose.yml; these differ from the older source. tsconfig.json, tsconfig.node.json, tailwind.config.js and postcss.config.js already match. Source README/INSTRUCTIONS/NOTES/open/setup text describes the earlier demo/OCR runtime and was not used to overwrite current KVR documentation. The integration report and contract explain final behavior.

Source-only legacy demo upload/homework pages and fixed-ratio compression UI were intentionally excluded. The older Studio batch transport/review implementation was superseded by KVR's newer shared-model generation pipeline; compatible strict count, option identity, competency constraints, bank management and school-audience improvements were adapted. Source historical implementation/automation reports were used as comparison guides, not as current test evidence.
