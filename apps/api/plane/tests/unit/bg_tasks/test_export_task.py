import pytest
import tracemalloc
from unittest.mock import patch, MagicMock, Mock
from plane.bgtasks.export_task import issue_export_task, create_zip_file
from plane.db.models import ExporterHistory, Issue, Project, ProjectMember
import io
import zipfile


@pytest.mark.unit
class TestExportTask:
    """Test the issue export task with progress tracking and memory constraints"""

    @pytest.fixture
    def project(self, create_user, workspace):
        """Create a test project"""
        project = Project.objects.create(
            name="Test Project",
            identifier="test-project",
            workspace=workspace
        )
        ProjectMember.objects.create(
            project=project,
            member=create_user,
            role=20,
            is_active=True
        )
        return project

    @pytest.fixture
    def exporter_history(self, workspace, create_user):
        """Create an ExporterHistory instance"""
        return ExporterHistory.objects.create(
            workspace=workspace,
            initiated_by=create_user,
            provider='csv',
            status='queued'
        )

    @pytest.fixture
    def mock_issues(self, workspace, project):
        """Create mock issues for testing"""
        issues = []
        for i in range(100):
            issue = Issue.objects.create(
                name=f"Test Issue {i}",
                workspace=workspace,
                project=project,
                description=f"Description for issue {i}",
            )
            issues.append(issue)
        return issues

    @pytest.mark.django_db
    def test_exporter_history_has_progress_fields(self, exporter_history):
        """Test that ExporterHistory model has the new progress tracking fields"""
        assert hasattr(exporter_history, 'progress_percentage')
        assert hasattr(exporter_history, 'total_items')
        assert hasattr(exporter_history, 'processed_items')
        assert exporter_history.progress_percentage == 0
        assert exporter_history.total_items == 0
        assert exporter_history.processed_items == 0

    @pytest.mark.django_db
    def test_exporter_history_progress_update(self, exporter_history):
        """Test updating progress fields on ExporterHistory"""
        exporter_history.total_items = 1000
        exporter_history.processed_items = 500
        exporter_history.progress_percentage = 50
        exporter_history.save()

        # Reload from database
        exporter_history.refresh_from_db()

        assert exporter_history.total_items == 1000
        assert exporter_history.processed_items == 500
        assert exporter_history.progress_percentage == 50

    @pytest.mark.django_db
    @patch('plane.bgtasks.export_task.upload_to_s3')
    def test_export_task_sets_total_items(
        self,
        mock_upload,
        workspace,
        project,
        exporter_history,
        mock_issues,
        create_user
    ):
        """Test that export task sets total_items correctly"""
        # Run the export task
        issue_export_task(
            provider='csv',
            workspace_id=workspace.id,
            project_ids=[str(project.id)],
            token_id=exporter_history.token,
            multiple=False,
            slug='test-export'
        )

        # Reload exporter history
        exporter_history.refresh_from_db()

        # Should have counted 100 issues
        assert exporter_history.total_items == 100
        assert exporter_history.processed_items == 100
        assert exporter_history.progress_percentage == 100

    @pytest.mark.django_db
    @patch('plane.bgtasks.export_task.upload_to_s3')
    def test_export_task_uses_chunked_for_large_exports(
        self,
        mock_upload,
        workspace,
        project,
        exporter_history,
        create_user
    ):
        """Test that export task uses chunked processing for >5000 issues"""
        # Create 6000 mock issues
        for i in range(6000):
            Issue.objects.create(
                name=f"Issue {i}",
                workspace=workspace,
                project=project,
            )

        with patch('plane.bgtasks.export_task.DataExporter.export_chunked') as mock_chunked:
            mock_chunked.return_value = ('test.csv', 'test,content')

            # Run the export task
            issue_export_task(
                provider='csv',
                workspace_id=workspace.id,
                project_ids=[str(project.id)],
                token_id=exporter_history.token,
                multiple=False,
                slug='test-export'
            )

            # Verify that export_chunked was called
            assert mock_chunked.called

        # Reload exporter history
        exporter_history.refresh_from_db()

        assert exporter_history.total_items == 6000

    @pytest.mark.django_db
    @patch('plane.bgtasks.export_task.upload_to_s3')
    def test_export_task_uses_regular_export_for_small_datasets(
        self,
        mock_upload,
        workspace,
        project,
        exporter_history,
        mock_issues,
        create_user
    ):
        """Test that export task uses regular export for <=5000 issues"""
        with patch('plane.bgtasks.export_task.DataExporter.export') as mock_export:
            mock_export.return_value = ('test.csv', 'test,content')

            # Run the export task
            issue_export_task(
                provider='csv',
                workspace_id=workspace.id,
                project_ids=[str(project.id)],
                token_id=exporter_history.token,
                multiple=False,
                slug='test-export'
            )

            # Verify that regular export was called
            assert mock_export.called

    def test_create_zip_file(self):
        """Test the create_zip_file function"""
        files = [
            ('file1.csv', 'content1'),
            ('file2.csv', 'content2'),
            ('file3.txt', b'binary content')
        ]

        zip_buffer = create_zip_file(files)

        # Verify it's a valid zip file
        assert isinstance(zip_buffer, io.BytesIO)
        zip_buffer.seek(0)

        with zipfile.ZipFile(zip_buffer, 'r') as zipf:
            # Should have 3 files
            assert len(zipf.namelist()) == 3
            assert 'file1.csv' in zipf.namelist()
            assert 'file2.csv' in zipf.namelist()
            assert 'file3.txt' in zipf.namelist()

            # Verify contents
            assert zipf.read('file1.csv').decode('utf-8') == 'content1'
            assert zipf.read('file2.csv').decode('utf-8') == 'content2'
            assert zipf.read('file3.txt') == b'binary content'

    def test_create_zip_file_memory_usage(self):
        """Test that create_zip_file doesn't use excessive memory"""
        tracemalloc.start()

        # Create multiple large files (simulating export output)
        files = []
        for i in range(10):
            # Each file is ~1MB of content
            content = f"Line {i}\n" * 50000
            files.append((f'file_{i}.csv', content))

        zip_buffer = create_zip_file(files)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / 1024 / 1024

        # Verify zip was created
        assert isinstance(zip_buffer, io.BytesIO)

        # Memory usage should stay reasonable (under 512MB)
        assert peak_mb < 512, f"Peak memory usage was {peak_mb:.2f} MB, expected < 512 MB"

    @pytest.mark.django_db
    @patch('plane.bgtasks.export_task.upload_to_s3')
    def test_export_task_handles_multiple_projects(
        self,
        mock_upload,
        workspace,
        project,
        exporter_history,
        create_user
    ):
        """Test export task with multiple projects"""
        # Create second project
        project2 = Project.objects.create(
            name="Test Project 2",
            identifier="test-project-2",
            workspace=workspace
        )
        ProjectMember.objects.create(
            project=project2,
            member=create_user,
            role=20,
            is_active=True
        )

        # Create issues in both projects
        for i in range(50):
            Issue.objects.create(
                name=f"Issue P1 {i}",
                workspace=workspace,
                project=project,
            )
        for i in range(30):
            Issue.objects.create(
                name=f"Issue P2 {i}",
                workspace=workspace,
                project=project2,
            )

        # Run export with multiple=True
        issue_export_task(
            provider='csv',
            workspace_id=workspace.id,
            project_ids=[str(project.id), str(project2.id)],
            token_id=exporter_history.token,
            multiple=True,
            slug='test-export'
        )

        # Reload exporter history
        exporter_history.refresh_from_db()

        # Should have counted all 80 issues
        assert exporter_history.total_items == 80
        assert exporter_history.processed_items == 80
        assert exporter_history.progress_percentage == 100

    @pytest.mark.django_db
    def test_export_task_handles_invalid_format(
        self,
        workspace,
        project,
        exporter_history,
        create_user
    ):
        """Test that export task handles invalid format gracefully"""
        # Run with invalid format
        issue_export_task(
            provider='invalid_format',
            workspace_id=workspace.id,
            project_ids=[str(project.id)],
            token_id=exporter_history.token,
            multiple=False,
            slug='test-export'
        )

        # Reload exporter history
        exporter_history.refresh_from_db()

        # Should be marked as failed
        assert exporter_history.status == 'failed'
        assert 'Unsupported format' in exporter_history.reason

    @pytest.mark.django_db
    @patch('plane.bgtasks.export_task.upload_to_s3')
    def test_export_task_all_formats(
        self,
        mock_upload,
        workspace,
        project,
        create_user,
        mock_issues
    ):
        """Test export task with all supported formats"""
        formats = ['csv', 'json', 'xlsx']

        for fmt in formats:
            exporter = ExporterHistory.objects.create(
                workspace=workspace,
                initiated_by=create_user,
                provider=fmt,
                status='queued'
            )

            issue_export_task(
                provider=fmt,
                workspace_id=workspace.id,
                project_ids=[str(project.id)],
                token_id=exporter.token,
                multiple=False,
                slug=f'test-export-{fmt}'
            )

            # Reload and verify
            exporter.refresh_from_db()
            assert exporter.total_items == 100, f"Failed for format {fmt}"
            assert exporter.processed_items == 100, f"Failed for format {fmt}"
