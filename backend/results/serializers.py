from rest_framework import serializers  # DRF serializer base classes
from .models import Result  # Result model


class ResultSerializer(serializers.ModelSerializer):
    test_case_input = serializers.CharField(source='test_case.input_data', read_only=True)  # show input instead of just ID
    test_case_expected = serializers.CharField(source='test_case.expected_output', read_only=True)  # show expected output

    class Meta:
        model = Result
        fields = [
            'id', 'submission', 'test_case_input', 'test_case_expected',
            'passed', 'actual_output', 'execution_time_ms', 'error_message'
        ]
