import pytest
import tracemalloc
from unittest.mock import MagicMock
from plane.utils.porters.exporter import DataExporter
from rest_framework import serializers


class SampleSerializer(serializers.Serializer):
    """Simple serializer for testing"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField()


@pytest.mark.unit
class TestDataExporterChunked:
    """Test the DataExporter chunked export functionality"""

    @pytest.fixture
    def mock_queryset(self):
        """Create a mock queryset with 10,000 items"""
        class MockQuerySet:
            def __init__(self, data):
                self.data = data
                self._result_cache = None

            def count(self):
                return len(self.data)

            def __getitem__(self, key):
                if isinstance(key, slice):
                    return MockQuerySet(self.data[key])
                return self.data[key]

            def __iter__(self):
                return iter(self.data)

        # Generate 10,000 mock issue objects
        data = []
        for i in range(10000):
            obj = MagicMock()
            obj.id = i
            obj.name = f"Issue {i}"
            obj.description = f"Description for issue {i}"
            data.append(obj)

        return MockQuerySet(data)

    @pytest.fixture
    def small_queryset(self):
        """Create a mock queryset with 100 items"""
        class MockQuerySet:
            def __init__(self, data):
                self.data = data

            def count(self):
                return len(self.data)

            def __getitem__(self, key):
                if isinstance(key, slice):
                    return MockQuerySet(self.data[key])
                return self.data[key]

            def __iter__(self):
                return iter(self.data)

        data = []
        for i in range(100):
            obj = MagicMock()
            obj.id = i
            obj.name = f"Issue {i}"
            obj.description = f"Description for issue {i}"
            data.append(obj)

        return MockQuerySet(data)

    def test_csv_chunked_export(self, small_queryset):
        """Test CSV export with chunked processing"""
        exporter = DataExporter(SampleSerializer, format_type='csv')
        filename, content = exporter.export_chunked('test', small_queryset, chunk_size=10)

        assert filename == 'test.csv'
        assert isinstance(content, str)
        assert 'Id,Name,Description' in content or 'id,name,description' in content
        # Should have 100 data rows + 1 header row
        assert len(content.split('\n')) >= 100

    def test_json_chunked_export(self, small_queryset):
        """Test JSON export with chunked processing"""
        exporter = DataExporter(SampleSerializer, format_type='json')
        filename, content = exporter.export_chunked('test', small_queryset, chunk_size=10)

        assert filename == 'test.json'
        assert isinstance(content, str)
        assert content.startswith('[')
        assert content.endswith(']')
        # Should have 100 items
        assert content.count('"id"') == 100

    def test_xlsx_chunked_export(self, small_queryset):
        """Test XLSX export with chunked processing"""
        exporter = DataExporter(SampleSerializer, format_type='xlsx')
        filename, content = exporter.export_chunked('test', small_queryset, chunk_size=10)

        assert filename == 'test.xlsx'
        assert isinstance(content, bytes)
        # XLSX files start with PK header (ZIP format)
        assert content[:2] == b'PK'

    def test_chunked_export_memory_usage_csv(self, mock_queryset):
        """Test that chunked CSV export keeps memory usage under 512MB"""
        tracemalloc.start()

        exporter = DataExporter(SampleSerializer, format_type='csv')
        filename, content = exporter.export_chunked('test', mock_queryset, chunk_size=1000)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Convert to MB
        peak_mb = peak / 1024 / 1024

        assert filename == 'test.csv'
        assert isinstance(content, str)
        # Memory should stay under 512MB
        assert peak_mb < 512, f"Peak memory usage was {peak_mb:.2f} MB, expected < 512 MB"

    def test_chunked_export_memory_usage_json(self, mock_queryset):
        """Test that chunked JSON export keeps memory usage under 512MB"""
        tracemalloc.start()

        exporter = DataExporter(SampleSerializer, format_type='json')
        filename, content = exporter.export_chunked('test', mock_queryset, chunk_size=1000)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / 1024 / 1024

        assert filename == 'test.json'
        assert isinstance(content, str)
        assert peak_mb < 512, f"Peak memory usage was {peak_mb:.2f} MB, expected < 512 MB"

    def test_chunked_export_memory_usage_xlsx(self, mock_queryset):
        """Test that chunked XLSX export keeps memory usage under 512MB"""
        tracemalloc.start()

        exporter = DataExporter(SampleSerializer, format_type='xlsx')
        filename, content = exporter.export_chunked('test', mock_queryset, chunk_size=1000)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / 1024 / 1024

        assert filename == 'test.xlsx'
        assert isinstance(content, bytes)
        assert peak_mb < 512, f"Peak memory usage was {peak_mb:.2f} MB, expected < 512 MB"

    def test_chunked_vs_regular_export_consistency_csv(self, small_queryset):
        """Verify chunked export produces same result as regular export for CSV"""
        exporter = DataExporter(SampleSerializer, format_type='csv')

        # Regular export
        _, regular_content = exporter.export('test', small_queryset)

        # Chunked export
        _, chunked_content = exporter.export_chunked('test', small_queryset, chunk_size=10)

        # Both should produce the same CSV content
        assert regular_content == chunked_content

    def test_chunked_vs_regular_export_consistency_json(self, small_queryset):
        """Verify chunked export produces similar structure to regular export for JSON"""
        exporter = DataExporter(SampleSerializer, format_type='json')

        # Regular export
        _, regular_content = exporter.export('test', small_queryset)

        # Chunked export
        _, chunked_content = exporter.export_chunked('test', small_queryset, chunk_size=10)

        # Both should have same number of items
        import json
        regular_data = json.loads(regular_content)
        chunked_data = json.loads(chunked_content)

        assert len(regular_data) == len(chunked_data) == 100
        # Verify first and last items match
        assert regular_data[0] == chunked_data[0]
        assert regular_data[-1] == chunked_data[-1]

    def test_chunked_export_with_empty_queryset(self):
        """Test chunked export with empty queryset"""
        class EmptyQuerySet:
            def count(self):
                return 0
            def __getitem__(self, key):
                return EmptyQuerySet()
            def __iter__(self):
                return iter([])

        exporter = DataExporter(SampleSerializer, format_type='csv')
        filename, content = exporter.export_chunked('test', EmptyQuerySet(), chunk_size=10)

        assert filename == 'test.csv'
        assert content == ''

    def test_chunked_export_without_format_type_raises_error(self, small_queryset):
        """Test that chunked export requires format_type"""
        exporter = DataExporter(SampleSerializer)

        with pytest.raises(ValueError, match="format_type must be provided"):
            exporter.export_chunked('test', small_queryset)

    def test_chunk_size_boundary_conditions(self, small_queryset):
        """Test chunked export with various chunk sizes"""
        exporter = DataExporter(SampleSerializer, format_type='csv')

        # Chunk size larger than dataset
        filename, content = exporter.export_chunked('test', small_queryset, chunk_size=1000)
        assert len(content.split('\n')) >= 100

        # Chunk size of 1
        filename, content = exporter.export_chunked('test', small_queryset, chunk_size=1)
        assert len(content.split('\n')) >= 100

        # Exact match chunk size
        filename, content = exporter.export_chunked('test', small_queryset, chunk_size=100)
        assert len(content.split('\n')) >= 100
