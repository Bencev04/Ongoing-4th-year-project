"""
Pydantic schemas for Maps Access Service API.

Defines request/response models for geocoding operations.
"""

from pydantic import BaseModel, Field

# ==============================================================================
# Request Schemas
# ==============================================================================


class GeocodeRequest(BaseModel):
    """Request schema for forward geocoding (address → coordinates)."""

    address: str = Field(..., min_length=1, max_length=500)


class ReverseGeocodeRequest(BaseModel):
    """Request schema for reverse geocoding (coordinates → address)."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class EircodeGeocodeRequest(BaseModel):
    """Request schema for Eircode geocoding."""

    eircode: str = Field(..., min_length=3, max_length=10)


# ==============================================================================
# Response Schemas
# ==============================================================================


class GeocodeResult(BaseModel):
    """Successful geocode response with coordinates and address details."""

    latitude: float
    longitude: float
    formatted_address: str
    eircode: str | None = None


class GeocodeResponse(BaseModel):
    """Standard geocode API response wrapper."""

    available: bool = True
    success: bool = True
    result: GeocodeResult | None = None
    error: str | None = None


class ServiceUnavailableResponse(BaseModel):
    """Response when the Google Maps API key is not configured."""

    available: bool = False
    success: bool = False
    result: None = None
    error: str = "Google Maps service is not configured"
