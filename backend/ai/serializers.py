from rest_framework import serializers  # DRF serializer base classes
from .models import RubricScore


class RubricScoreSerializer(serializers.ModelSerializer):
    total_score = serializers.IntegerField(read_only=True)  # computed 0-8 property

    class Meta:
        model = RubricScore
        fields = [
            'submission',
            'correctness_score', 'correctness_note',
            'code_quality_score', 'code_quality_note',
            'approach_score', 'approach_note',
            'edge_case_score', 'edge_case_note',
            'overall_feedback', 'total_score',
            'model_used', 'created_at',
        ]
