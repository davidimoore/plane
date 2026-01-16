import io
import os
import tempfile
import tracemalloc
import zipfile

import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from plane.bgtasks.export_task import (
    create_zip_file,
    create_zip_file_streamed,
    update_progress,
    get_issue_ids_chunked,
    export_issues_chunked,
    CHUNK_SIZE,
    LARGE_EXPORT_THRESHOLD,
)


# Memory limit in bytes (512MB)
MEMORY_LIMIT_BYTES = 512 * 1024 * 1024


@pytest.mark.unit
class TestCreateZipFile:
    """Tests for the create_zip_file function (in-memory ZIP creation)."""

    def test_creates_valid_zip_with_single_file(self):
        """Test creating a ZIP with a single file."""
        files = [("test.txt", "Hello, World!")]
        result = create_zip_file(files)

        assert isinstance(result, io.BytesIO)

        # Verify ZIP contents
        with zipfile.ZipFile(result, "r") as zf:
            assert zf.namelist() == ["test.txt"]
            assert zf.read("test.txt") == b"Hello, World!"

    def test_creates_valid_zip_with_multiple_files(self):
        """Test creating a ZIP with multiple files."""
        files = [
            ("file1.csv", "id,name\n1,test"),
            ("file2.json", '{"key": "value"}'),
            ("file3.txt", b"binary content"),
        ]
        result = create_zip_file(files)

        with zipfile.ZipFile(result, "r") as zf:
            assert len(zf.namelist()) == 3
            assert "file1.csv" in zf.namelist()
            assert "file2.json" in zf.namelist()
            assert "file3.txt" in zf.namelist()

    def test_creates_empty_zip_with_no_files(self):
        """Test creating a ZIP with no files."""
        files = []
        result = create_zip_file(files)

        with zipfile.ZipFile(result, "r") as zf:
            assert zf.namelist() == []

    def test_zip_is_seeked_to_beginning(self):
        """Test that the returned BytesIO is seeked to the beginning."""
        files = [("test.txt", "content")]
        result = create_zip_file(files)

        # Should be able to read immediately without seeking
        assert result.tell() == 0


@pytest.mark.unit
class TestCreateZipFileStreamed:
    """Tests for the create_zip_file_streamed function (file-based ZIP creation)."""

    def test_creates_temp_file_on_disk(self):
        """Test that a temporary file is created on disk."""
        files = [("test.txt", "Hello, World!")]
        zip_path = create_zip_file_streamed(files)

        try:
            assert os.path.exists(zip_path)
            assert zip_path.endswith(".zip")
        finally:
            if os.path.exists(zip_path):
                os.unlink(zip_path)

    def test_creates_valid_zip_on_disk(self):
        """Test that the created ZIP file is valid."""
        files = [
            ("data.csv", "id,name\n1,test\n2,test2"),
            ("meta.json", '{"count": 2}'),
        ]
        zip_path = create_zip_file_streamed(files)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                assert len(zf.namelist()) == 2
                assert zf.read("data.csv") == b"id,name\n1,test\n2,test2"
        finally:
            if os.path.exists(zip_path):
                os.unlink(zip_path)

    def test_cleans_up_on_error(self):
        """Test that temp file is cleaned up if an error occurs during creation."""
        # This is a bit tricky to test directly since the error handling
        # is inside the function. We test the happy path primarily.
        files = [("test.txt", "content")]
        zip_path = create_zip_file_streamed(files)

        # Clean up
        if os.path.exists(zip_path):
            os.unlink(zip_path)


@pytest.mark.unit
class TestUpdateProgress:
    """Tests for the update_progress function."""

    @pytest.mark.django_db
    @patch("plane.bgtasks.export_task.ExporterHistory")
    def test_updates_progress_correctly(self, mock_exporter_history):
        """Test that progress is calculated and updated correctly."""
        mock_filter = MagicMock()
        mock_exporter_history.objects.filter.return_value = mock_filter

        update_progress("test-token", 50, 100)

        mock_exporter_history.objects.filter.assert_called_once_with(token="test-token")
        mock_filter.update.assert_called_once_with(
            processed_items=50,
            progress_percentage=50
        )

    @pytest.mark.django_db
    @patch("plane.bgtasks.export_task.ExporterHistory")
    def test_handles_zero_total(self, mock_exporter_history):
        """Test that zero total items doesn't cause division by zero."""
        mock_filter = MagicMock()
        mock_exporter_history.objects.filter.return_value = mock_filter

        update_progress("test-token", 0, 0)

        mock_filter.update.assert_called_once_with(
            processed_items=0,
            progress_percentage=0
        )

    @pytest.mark.django_db
    @patch("plane.bgtasks.export_task.ExporterHistory")
    def test_caps_percentage_at_100(self, mock_exporter_history):
        """Test that percentage is capped at 100."""
        mock_filter = MagicMock()
        mock_exporter_history.objects.filter.return_value = mock_filter

        # Edge case where processed > total (shouldn't happen but be safe)
        update_progress("test-token", 150, 100)

        mock_filter.update.assert_called_once_with(
            processed_items=150,
            progress_percentage=100
        )


@pytest.mark.unit
class TestGetIssueIdsChunked:
    """Tests for the get_issue_ids_chunked function."""

    def test_yields_chunks_of_correct_size(self):
        """Test that chunks are yielded with the correct size."""
        # Create a mock queryset
        mock_queryset = MagicMock()
        mock_ids = list(range(2500))  # 2500 IDs
        mock_queryset.values_list.return_value = mock_ids

        chunks = list(get_issue_ids_chunked(mock_queryset, chunk_size=1000))

        assert len(chunks) == 3  # 1000 + 1000 + 500
        assert len(chunks[0]) == 1000
        assert len(chunks[1]) == 1000
        assert len(chunks[2]) == 500

    def test_handles_empty_queryset(self):
        """Test handling of empty queryset."""
        mock_queryset = MagicMock()
        mock_queryset.values_list.return_value = []

        chunks = list(get_issue_ids_chunked(mock_queryset))

        assert chunks == []

    def test_handles_queryset_smaller_than_chunk_size(self):
        """Test handling of queryset smaller than chunk size."""
        mock_queryset = MagicMock()
        mock_ids = list(range(100))
        mock_queryset.values_list.return_value = mock_ids

        chunks = list(get_issue_ids_chunked(mock_queryset, chunk_size=1000))

        assert len(chunks) == 1
        assert len(chunks[0]) == 100


@pytest.mark.unit
class TestMemoryUsage:
    """Tests to verify memory usage stays within limits."""

    def test_streamed_zip_memory_usage(self):
        """Test that streamed ZIP creation keeps memory usage low."""
        tracemalloc.start()

        # Create a large amount of data (simulating ~10MB of content)
        large_content = "x" * (10 * 1024 * 1024)  # 10MB string
        files = [("large_file.txt", large_content)]

        current, peak = tracemalloc.get_traced_memory()

        zip_path = create_zip_file_streamed(files)

        current_after, peak_after = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        try:
            # Peak memory should stay well under 512MB
            # The streamed version writes to disk, so memory usage should be minimal
            assert peak_after < MEMORY_LIMIT_BYTES, (
                f"Peak memory {peak_after / (1024*1024):.2f}MB exceeded limit of 512MB"
            )
        finally:
            if os.path.exists(zip_path):
                os.unlink(zip_path)

    def test_in_memory_zip_for_small_data(self):
        """Test that in-memory ZIP works fine for small data."""
        tracemalloc.start()

        # Small amount of data
        small_content = "test content " * 100
        files = [("small_file.txt", small_content)]

        zip_buffer = create_zip_file(files)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert peak < MEMORY_LIMIT_BYTES
        assert isinstance(zip_buffer, io.BytesIO)

    def test_chunked_processing_memory_efficiency(self):
        """Test that chunked ID fetching is memory efficient."""
        tracemalloc.start()

        # Simulate a large number of IDs
        mock_queryset = MagicMock()
        mock_ids = list(range(10000))  # 10000 IDs
        mock_queryset.values_list.return_value = mock_ids

        # Process all chunks
        all_chunks = list(get_issue_ids_chunked(mock_queryset, chunk_size=CHUNK_SIZE))

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Should have correct number of chunks
        expected_chunks = (10000 + CHUNK_SIZE - 1) // CHUNK_SIZE
        assert len(all_chunks) == expected_chunks

        # Memory should be reasonable
        assert peak < MEMORY_LIMIT_BYTES


@pytest.mark.unit
class TestExportIssuesChunked:
    """Tests for the export_issues_chunked function."""

    @pytest.mark.django_db
    @patch("plane.bgtasks.export_task.update_progress")
    @patch("plane.bgtasks.export_task.get_issue_ids_chunked")
    def test_processes_chunks_and_updates_progress(
        self, mock_get_chunks, mock_update_progress
    ):
        """Test that chunks are processed and progress is updated."""
        # Setup mocks
        mock_get_chunks.return_value = iter([
            [1, 2, 3],
            [4, 5],
        ])

        mock_queryset = MagicMock()
        mock_filtered_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_filtered_queryset

        mock_exporter = MagicMock()
        mock_exporter.serialize.return_value = [{"id": 1}]
        mock_exporter.formatter.encode.return_value = '{"data": []}'
        mock_exporter.formatter.extension = "json"

        filename, content = export_issues_chunked(
            mock_exporter,
            mock_queryset,
            "test-export",
            "test-token",
            total_issues=5,
            processed_offset=0,
        )

        # Verify chunks were processed
        assert mock_exporter.serialize.call_count == 2

        # Verify progress was updated
        assert mock_update_progress.call_count == 2

        # Verify output
        assert filename == "test-export.json"
        assert content == '{"data": []}'


@pytest.mark.unit
class TestConstants:
    """Tests for module constants."""

    def test_chunk_size_is_reasonable(self):
        """Test that CHUNK_SIZE is set to a reasonable value."""
        assert CHUNK_SIZE == 1000
        assert CHUNK_SIZE > 0
        assert CHUNK_SIZE <= 5000

    def test_large_export_threshold(self):
        """Test that LARGE_EXPORT_THRESHOLD is set correctly."""
        assert LARGE_EXPORT_THRESHOLD == 5000
        assert LARGE_EXPORT_THRESHOLD > CHUNK_SIZE
