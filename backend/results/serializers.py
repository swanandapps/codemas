from rest_framework import serializers  # DRF serializer base classes
from .models import Result  # Result model


class ResultSerializer(serializers.ModelSerializer):
    test_case_input = serializers.CharField(source='test_case.input_data', read_only=True)  # show input instead of just ID
    test_case_expected = serializers.CharField(source='test_case.expected_output', read_only=True)  # show expected output

    class Meta:
        model = Result
        fields = [
            'id', 'submission', 'test_case_input', 'test_case_expected',
            'passed', 'actual_output', 'execution_time_ms', 'error_message', 'is_hidden'
        ]

    is_hidden = serializers.BooleanField(source='test_case.is_hidden', read_only=True)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # A hidden test's input and expected output never reach a non-staff viewer.
        if instance.test_case.is_hidden and not self.context.get('show_hidden', False):
            data['test_case_input'] = None
            data['test_case_expected'] = None
        return data
