"""Pydantic models for classification prediction artifacts."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ClassificationPrediction(BaseModel):
    """Prediction artifact for classification tasks.
    
    Contains the model's prediction along with metadata for reproducibility
    and evaluation purposes.
    """
    dataset_version: str = Field(default="v1.0", description="Version of the dataset used")
    split_name: str = Field(..., description="Name of the data split (train/validation/test)")
    example_id: str = Field(..., description="Unique identifier for the example")
    gold_label: str = Field(..., description="True label from the ground truth")
    predicted_label: str = Field(..., description="Predicted label from the model")
    is_valid_output: bool = Field(..., description="Whether the prediction meets quality criteria")
    error_category: Optional[str] = Field(None, description="Category of error if invalid")
    inference_latency_ms: float = Field(..., description="Latency in milliseconds")
    model_id: str = Field(..., description="Identifier of the model used")
    prompt_version: str = Field(..., description="Version of the classification prompt")
    prompt_fingerprint: str = Field(..., description="SHA256 hash of the prompt")
    evaluation_timestamp: datetime = Field(default_factory=datetime.now)

    def __getitem__(self, key: str):
        """Dict-style access: ``pred["gold_label"]``."""
        if key in type(self).model_fields:
            return getattr(self, key)
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        """Support ``"field" in pred``."""
        return key in type(self).model_fields


class ClassificationArtifact(BaseModel):
    """Complete prediction artifact containing all metadata about a classification result."""
    prediction: ClassificationPrediction
    metadata: dict
    
    class Config:
        arbitrary_types_allowed = True
